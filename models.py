from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Users(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    apples = db.Column(db.Integer, nullable=True)
    monies = db.Column(db.Integer, nullable=True)

class Trades(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    partyA = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    partyB = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    apples = db.Column(db.Integer, nullable=True)
    monies = db.Column(db.Integer, nullable=True)
    timeOffset = db.Column(db.Integer, nullable=True)

class MinuteUpdates(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    party = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    timeOffset = db.Column(db.Integer, nullable=True)
    apples = db.Column(db.Integer, nullable=True, default=0)

class GameState(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    start_time = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=False)
    last_tick = db.Column(db.DateTime, nullable=True) # Last time resources were given

class FarmerDiscards(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    party = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    timeOffset = db.Column(db.Integer, nullable=True)
    apples = db.Column(db.Integer, nullable=True, default=0)


def minuteUpdate(current_offset):
    # Find all update instructions for this specific minute
    print("minute update", current_offset)
    updates = MinuteUpdates.query.filter_by(timeOffset=current_offset).all()

    for update in updates:
        # Find the specific user this update belongs to
        user = Users.query.get(update.party)
        if user:
            # Apply the changes (defaulting to 0 if the column is None)
            if user.username.startswith("F"):
                current_apples = user.apples or 0
                if current_offset > 0:
                    discarded = max(0, current_apples - 100)
                    if discarded > 0:
                        existing_discard = FarmerDiscards.query.filter_by(
                            party=user.id, timeOffset=current_offset - 1
                        ).first()
                        if existing_discard:
                            existing_discard.apples += discarded
                        else:
                            db.session.add(FarmerDiscards(
                                party=user.id,
                                timeOffset=current_offset - 1,
                                apples=discarded
                            ))
                user.apples = min(100, current_apples)
                user.apples = (user.apples or 0) + (update.apples or 0)

def tick_game():
    state = GameState.query.first()
    if not state or not state.is_active:
        return

    now = datetime.now()

    # Calculate how many minutes have passed since the game started
    # This is our current "Time Offset"
    total_seconds_since_start = (now - state.start_time).total_seconds()
    current_game_minute = int(total_seconds_since_start // 60)

    # Check if we need to tick (if current minute is ahead of the last recorded tick)
    # We use a 'last_tick_minute' concept here
    if state.last_tick is None or now >= state.last_tick + timedelta(seconds=60):
        # Calculate how many intervals we missed (usually 1, but handles lag)
        seconds_passed_since_last_tick = (now - (state.last_tick or state.start_time)).total_seconds()
        intervals = int(seconds_passed_since_last_tick // 60)

        if intervals > 0:
            # If the server lagged and skipped minutes, apply all of them in order
            last_minute_processed = int(
                (state.last_tick - state.start_time).total_seconds() // 60) if state.last_tick else -1

            for m in range(last_minute_processed + 1, current_game_minute + 1):
                minuteUpdate(m)

            # Update last_tick to the current minute mark
            state.last_tick = (state.last_tick or state.start_time) + timedelta(minutes=intervals)
            db.session.commit()


def addUser(name, apples, monies):
    # Ensure values are integers to prevent DB errors
    new_entry = Users(
        username=name,
        apples=int(apples or 0),
        monies=int(monies or 0)
    )
    print(f"DEBUG: Successfully added {name, apples, monies}.")
    db.session.add(new_entry)


def addUsers(noFarmers, noAppleMakers, noConsumers):
    try:
        # Convert inputs to integers once at the start
        f_count = int(noFarmers or 0)
        a_count = int(noAppleMakers or 0)
        c_count = int(noConsumers or 0)

        for i in range(f_count):
            addUser(f"F{i}", 0, 0)
        for i in range(a_count):
            addUser(f"A{i}", 0, 30000)
        for i in range(c_count):
            addUser(f"C{i}", 0, 100000)

        db.session.commit()  # The crucial save
        print(f"DEBUG: Successfully added {f_count + a_count + c_count} users.")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"DEBUG ERROR: {e}")
        return False


def validate_role(user, delta_apples, delta_monies):
    """
    Checks if the proposed changes would result in negative balances.
    Returns error message if invalid, else None.
    """
    if user.username.startswith("F") and delta_apples > 0:
        return f"User {user.username} can only sell apples."

    if user.username.startswith("C") and delta_apples < 0:
        return f"User {user.username} can only buy apples."

    if (user.apples + delta_apples) < 0:
        return f"User {user.username} has insufficient apples."

    if (user.monies + delta_monies) < 0:
        return f"User {user.username} has insufficient funds."

    return None


def execute_trade(name_a, name_b, t_offset, price, volume):
    """Execute an apple trade between taker `name_a` and maker `name_b`.

    `name_a` is the taker (a Farmer or Consumer), `name_b` the Apple Maker.
    A positive `volume` means the taker buys apples from the maker; a negative
    `volume` means the taker sells apples to the maker.

    Returns (ok, message). Nothing is committed when ok is False.
    """
    try:
        t_offset = int(t_offset or 0)
        price = int(price or 0)
        volume = int(volume or 0)

        if price <= 0:
            return False, "Error: Price must be positive."
        if volume == 0:
            return False, "Error: Volume cannot be zero."

        money_total = price * volume
        dA = volume

        user_a = Users.query.filter_by(username=name_a).first()
        user_b = Users.query.filter_by(username=name_b).first()

        if not user_a or not user_b:
            return False, "Error: One or both users not found."

        if user_a.username[0] == 'A':
            return False, f"Error: {user_a.username} is a market maker and must always be Party B."

        if user_b.username[0] != 'A':
            return False, f"Error: {user_b.username} is not a market maker — Party B must be an Apple Maker (A)."

        state = GameState.query.first()
        now = datetime.now()
        current_game_minute = 0
        if state and state.is_active and state.start_time:
            current_game_minute = int((now - state.start_time).total_seconds() // 60)

        # For late farmer apple sales, include discarded apples in validation
        is_late_farmer_apple_sale = (
            user_a.username.startswith("F") and
            dA < 0 and
            current_game_minute > t_offset
        )
        farmer_discard_record = None
        discard_apples = 0
        if is_late_farmer_apple_sale:
            farmer_discard_record = FarmerDiscards.query.filter_by(
                party=user_a.id, timeOffset=t_offset
            ).first()
            discard_apples = farmer_discard_record.apples if farmer_discard_record else 0
            user_a.apples = (user_a.apples or 0) + discard_apples

        error_a = validate_role(user_a, dA, -money_total)

        if is_late_farmer_apple_sale:
            user_a.apples = (user_a.apples or 0) - discard_apples  # restore

        if error_a:
            return False, error_a

        # Party B: Loses apples, Gains money
        error_b = validate_role(user_b, -dA, money_total)
        if error_b:
            return False, error_b

        # If everything passes:
        if is_late_farmer_apple_sale and discard_apples > 0:
            absorbed = min(discard_apples, -dA)
            farmer_discard_record.apples -= absorbed
            user_a.apples = (user_a.apples or 0) + dA + absorbed
        else:
            user_a.apples += dA
        user_b.apples -= dA
        user_a.monies -= money_total
        user_b.monies += money_total

        new_trade = Trades(
            partyA=user_a.id,
            partyB=user_b.id,
            apples=dA,
            monies=-money_total,
            timeOffset=t_offset
        )
        db.session.add(new_trade)
        db.session.commit()

        resource = "🍎 Apples"
        if volume > 0:
            summary = f"Trade Executed: {name_a} bought {abs(volume)} {resource} from {name_b} at ${price:.2f} (Total: ${abs(money_total):.2f}) at T+{t_offset}m"
        else:
            summary = f"Trade Executed: {name_a} sold {abs(volume)} {resource} to {name_b} at ${price:.2f} (Total: ${abs(money_total):.2f}) at T+{t_offset}m"
        return True, summary

    except Exception as e:
        db.session.rollback()
        return False, f"System Error: {str(e)}"


def generateFarmer(id, l):
    for index, item in enumerate(l):
        update = MinuteUpdates(party = id, timeOffset = index, apples = item)
        db.session.add(update)

def generateConsumer(id, l):
    # Targets are issued per 3-minute block (minutes 0-2, 3-5, ...).
    # Each block target is the combined apple demand across its minutes.
    block = 3
    for start in range(0, len(l), block):
        chunk = l[start:start + block]
        update = MinuteUpdates(party = id, timeOffset = start, apples = sum(chunk))
        db.session.add(update)

def generate_schedule():
    users = Users.query.all()
    farmerCount = 0
    farmerLists = [
        [10,120,30,100,20,110,90,10,20,120,40,90,80,55,50],
        [100,15,105,25,120,15,10,130,60,95,30,65,10,90,75],
        [60,130,10,100,45,115,20,70,125,15,90,35,110,10,10],
        [120,20,95,10,105,30,110,15,60,130,25,80,10,100,35]
    ]

    consumerCount = 0
    consumerLists = [
        [80,60,60,20,10,10,60,70,50,50,40,50,40,40,40],
        [20,20,20,80,70,70,30,20,20,40,30,40,80,70,70],
        [40,40,40,50,60,50,80,70,80,30,20,20,40,30,30],
        [30,30,30,70,60,70,20,20,20,70,70,70,40,40,40],
    ]
    for user in users:
        if user.username.startswith("F"):
            generateFarmer(user.id, farmerLists[farmerCount])
            if farmerCount + 1 < len(farmerLists):
                farmerCount += 1
        if user.username.startswith("C"):
            generateConsumer(user.id, consumerLists[consumerCount])
            if consumerCount + 1 < len(consumerLists):
                consumerCount += 1

    db.session.commit()


RESULT_CATEGORIES = {
    'F': 'Farmers (F)',
    'A': 'AppleMakers (A)',
    'C': 'Consumers (C)',
}


def consumer_fulfillment(user):
    """How well a consumer met its 3-minute block targets.

    Returns (earned_points, possible_points, fulfillment_percentage).
    """
    total_possible_points = 0
    total_earned_points = 0

    # Each MinuteUpdates row is the target for one 3-minute block
    updates = MinuteUpdates.query.filter_by(party=user.id).all()

    for up in updates:
        m = up.timeOffset
        target_apples = max(0, up.apples or 0)

        if target_apples == 0:
            continue

        total_possible_points += target_apples

        # Find all trades this user did within this 3-minute block
        trades_this_block = Trades.query.filter(
            ((Trades.partyA == user.id) | (Trades.partyB == user.id)),
            (Trades.timeOffset >= m),
            (Trades.timeOffset <= m + 2)
        ).all()

        # Calculate what they actually bought during this block
        bought_apples = 0
        for tr in trades_this_block:
            if tr.partyA == user.id:
                bought_apples += (tr.apples or 0)
            else:
                # PartyB is the Maker (Inverse delta)
                bought_apples -= (tr.apples or 0)

        # Cap the fulfillment: you can't earn more than the block target
        earned_apples = min(max(0, bought_apples), target_apples)
        total_earned_points += earned_apples

    fulfillment = (total_earned_points / total_possible_points * 100) if total_possible_points > 0 else 0
    return total_earned_points, total_possible_points, round(fulfillment, 2)


def compute_results():
    """Build per-category rankings plus consumer fulfillment scores."""
    results_data = {
        'Farmers (F)': [],
        'AppleMakers (A)': [],
        'Consumers (C)': []
    }

    for u in Users.query.all():
        prefix = u.username[0]
        category = RESULT_CATEGORIES.get(prefix)

        if not category:
            continue

        if prefix != 'C':
            # Standard ranking for non-consumers
            results_data[category].append({
                'username': u.username,
                'monies': u.monies or 0,
                'apples': u.apples or 0
            })
        else:
            earned, possible, fulfillment = consumer_fulfillment(u)
            results_data[category].append({
                'username': u.username,
                'monies': u.monies or 0,
                'fulfillment': fulfillment,
                'score': earned,
                'max_score': possible
            })

    # Sort the lists
    for key in results_data:
        if key == 'Consumers (C)':
            # Rank 1: Fulfillment % | Rank 2: Final Money
            results_data[key].sort(key=lambda x: (x['fulfillment'], x['monies']), reverse=True)
        else:
            results_data[key].sort(key=lambda x: x['monies'], reverse=True)

    return results_data


def compute_trade_highlights():
    """Compute the hall-of-fame records across all apple trades."""
    h = {
        'apple_best_buy': None, 'apple_worst_buy': None,
        'apple_best_sell': None, 'apple_worst_sell': None,
        'apple_big': None
    }

    for t in Trades.query.all():
        raw_vol = t.apples
        if not raw_vol:
            continue

        abs_vol = abs(raw_vol)
        price = abs(t.monies / raw_vol)

        # 1. Volume Record (Either direction)
        if not h['apple_big'] or abs_vol > abs(h['apple_big'].apples):
            h['apple_big'] = t

        # 2. Buy Records (Taker A bought, so raw_vol > 0)
        if raw_vol > 0:
            # Best Buy = Lowest Price
            if not h['apple_best_buy'] or price < abs(h['apple_best_buy'].monies / h['apple_best_buy'].apples):
                h['apple_best_buy'] = t
            # Worst Buy = Highest Price
            if not h['apple_worst_buy'] or price > abs(h['apple_worst_buy'].monies / h['apple_worst_buy'].apples):
                h['apple_worst_buy'] = t

        # 3. Sell Records (Taker A sold, so raw_vol < 0)
        else:
            # Best Sell = Highest Price
            if not h['apple_best_sell'] or price > abs(h['apple_best_sell'].monies / h['apple_best_sell'].apples):
                h['apple_best_sell'] = t
            # Worst Sell = Lowest Price
            if not h['apple_worst_sell'] or price < abs(h['apple_worst_sell'].monies / h['apple_worst_sell'].apples):
                h['apple_worst_sell'] = t

    return h


def consumer_block_bought(user, block_start):
    """Net apples a consumer has bought within the given 3-minute block."""
    trades = Trades.query.filter(
        ((Trades.partyA == user.id) | (Trades.partyB == user.id)),
        (Trades.timeOffset >= block_start),
        (Trades.timeOffset <= block_start + 2)
    ).all()
    bought = 0
    for tr in trades:
        if tr.partyA == user.id:
            bought += (tr.apples or 0)
        else:
            bought -= (tr.apples or 0)
    return bought


def consumer_block_remaining(user, current_minute):
    """Outstanding apple demand for the current block, as a non-positive number.

    Starts at -target and moves toward 0 as the consumer buys apples; 0 once met.
    """
    block_start = (current_minute // 3) * 3
    target_row = MinuteUpdates.query.filter_by(
        party=user.id, timeOffset=block_start
    ).first()
    target = max(0, (target_row.apples or 0) if target_row else 0)
    if target == 0:
        return 0
    bought = consumer_block_bought(user, block_start)
    remaining = max(0, target - bought)
    return -remaining


def game_clock():
    """Return (is_active, elapsed_seconds, current_minute) for the running game."""
    state = GameState.query.first()
    is_active = bool(state and state.is_active)
    elapsed_seconds = 0
    if state and state.start_time:
        elapsed_seconds = max(0, int((datetime.now() - state.start_time).total_seconds()))
    current_minute = elapsed_seconds // 60
    return is_active, elapsed_seconds, current_minute


def dashboard_trades(limit=50):
    """Recent apple trades, newest first, as display dicts."""
    trades = Trades.query.order_by(Trades.id.desc()).limit(limit).all()
    out = []
    for t in trades:
        if not t.apples or not t.monies:
            continue
        out.append({
            'is_sell': t.apples < 0,
            'price': round(abs(t.monies / t.apples), 2),
            'size': abs(t.apples),
        })
    return out


def dashboard_users(current_minute):
    """All users with apple and money counts.

    Consumers report their outstanding block target as a negative number
    instead of an inventory count.
    """
    out = []
    for u in Users.query.order_by(Users.username).all():
        prefix = u.username[0]
        if prefix == 'C':
            apples = consumer_block_remaining(u, current_minute)
            role = 'consumer'
        else:
            apples = u.apples or 0
            role = 'farmer' if prefix == 'F' else 'maker'
        out.append({
            'username': u.username,
            'apples': apples,
            'monies': u.monies or 0,
            'role': role,
        })
    return out