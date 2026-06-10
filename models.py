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
            addUser(f"A{i}", 0, 20000)
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
        [50,70,60,10,10,100,100,50,30,50,20,90,90,60,50],
        [50,70,60,10,10,100,90,50,30,60,20,100,90,50,50],
        [50,60,70,20,10,90,100,50,30,50,10,90,100,60,50],
        [50,60,70,20,10,90,90,50,30,60,10,100,100,50,50]
    ]

    consumerCount = 0
    consumerLists = [
        [40,50,40,20,80,60,10,20,40,150,10,10,70,50,40],
        [50,40,20,40,60,80,10,40,20,140,20,10,60,30,40],
        [50,40,60,80,20,40,10,20,40,150,10,10,50,50,50],
        [40,50,80,60,40,20,10,40,20,140,20,10,50,80,30],
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
