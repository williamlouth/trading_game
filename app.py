
from flask import flash, get_flashed_messages  # Ensure these are imported at the top
from flask import Flask, request, render_template_string, redirect
import os
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta

# Initialize the Flask application
app = Flask(__name__)
app.secret_key = 'super_secret_market_key'

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'sqlite.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class Users(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    apples = db.Column(db.Integer, nullable=True)
    juices = db.Column(db.Integer, nullable=True)
    monies = db.Column(db.Integer, nullable=True)

class Trades(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    partyA = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    partyB = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    apples = db.Column(db.Integer, nullable=True)
    juices = db.Column(db.Integer, nullable=True)
    monies = db.Column(db.Integer, nullable=True)
    timeOffset = db.Column(db.Integer, nullable=True)

class MinuteUpdates(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    party = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    timeOffset = db.Column(db.Integer, nullable=True)
    apples = db.Column(db.Integer, nullable=True, default=0)
    juices = db.Column(db.Integer, nullable=True, default=0)
    monies = db.Column(db.Integer, nullable=True, default=0)

class GameState(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    start_time = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=False)
    last_tick = db.Column(db.DateTime, nullable=True) # Last time resources were given
    production_rate = db.Column(db.Integer, default=50 )
    producer_limit = db.Column(db.Integer, default=100 )

class ProducerUpdates(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    party = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    timeOffset = db.Column(db.Integer, nullable=True)
    apples = db.Column(db.Integer, nullable=True, default=0)

class FarmerDiscards(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    party = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    timeOffset = db.Column(db.Integer, nullable=True)
    apples = db.Column(db.Integer, nullable=True, default=0)

with app.app_context():
    db.create_all()
    print("Database and tables created")

# Define a "route" (the URL path) and the function that handles it

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
                user.juices = (user.juices or 0) + (update.juices or 0)
                user.monies = (user.monies or 0) + (update.monies or 0)

    users = Users.query.all()
    state = GameState.query.first()
    rate = state.production_rate if state else 50
    for u in users:
        if u.username.startswith("P"):
            produced = min(u.apples, rate)
            produceUpdate = ProducerUpdates(party = u.id, timeOffset = current_offset, apples = produced)
            db.session.add(produceUpdate)
            u.apples -= produced
            u.juices += produced


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
            
@app.before_request
def pulse():
    # Only pulse on specific routes to save database overhead
    if request.endpoint in ['dashboard','consumer_targets']:
        tick_game()
        
@app.route('/')
def hello_world():
    index_html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Trading Game Terminal</title>
        <style>
            body { 
                font-family: 'Courier New', Courier, monospace; 
                background: #0a0a0a; 
                color: #ffffff; 
                display: flex; 
                justify-content: center; 
                align-items: center; 
                height: 100vh; 
                margin: 0; 
                overflow: hidden;
            }
            .welcome-container { 
                text-align: center; 
                padding: 60px; 
                border: 1px solid #333; 
                background: linear-gradient(145deg, #111, #050505); 
                box-shadow: 0 0 50px rgba(0, 0, 0, 0.5);
                max-width: 700px;
                border-radius: 4px;
            }
            .logo {
                font-size: 3.5rem;
                font-weight: bold;
                letter-spacing: 10px;
                margin-bottom: 20px;
                background: linear-gradient(to right, #00ff88, #007bff);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }
            .divider {
                height: 2px;
                width: 100px;
                background: #00ff88;
                margin: 20px auto;
            }
            h2 { 
                font-size: 1.2rem; 
                color: #888; 
                text-transform: uppercase; 
                letter-spacing: 5px;
                margin-top: 0;
            }
            p { 
                color: #666; 
                font-size: 1rem; 
                line-height: 1.6;
                margin-top: 20px;
            }
            .status-line {
                margin-top: 40px;
                font-size: 0.7rem;
                color: #222;
                text-transform: uppercase;
            }
        </style>
    </head>
    <body>
        <div class="welcome-container">
            <div class="logo">THE TRADING GAME</div>
            <div class="divider"></div>
            <p>
                Welcome to the Apple & Juice exchange. <br>
                Monitor the tape, fill your targets, and manage your capital.
            </p>
        </div>
    </body>
    </html>
    '''
    return render_template_string(index_html)


def addUser(name, apples, juices, monies):
    # Ensure values are integers to prevent DB errors
    new_entry = Users(
        username=name,
        apples=int(apples or 0),
        juices=int(juices or 0),
        monies=int(monies or 0)
    )
    print(f"DEBUG: Successfully added {name, apples, juices, monies}.")
    db.session.add(new_entry)


def addUsers(noFarmers, noAppleMakers, noProducers, noJuiceMakers, noConsumers):
    try:
        # Convert inputs to integers once at the start
        f_count = int(noFarmers or 0)
        a_count = int(noAppleMakers or 0)
        p_count = int(noProducers or 0)
        j_count = int(noJuiceMakers or 0)
        c_count = int(noConsumers or 0)

        for i in range(f_count):
            addUser(f"F{i}", 0, 0, 0)
        for i in range(a_count):
            addUser(f"A{i}", 0, 0, 20000)
        for i in range(p_count):
            addUser(f"P{i}", 0, 50, 10000)
        for i in range(j_count):
            addUser(f"J{i}", 0, 0, 20000)
        for i in range(c_count):
            addUser(f"C{i}", 0, 0, 100000)

        db.session.commit()  # The crucial save
        print(f"DEBUG: Successfully added {f_count + a_count + p_count + j_count + c_count} users.")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"DEBUG ERROR: {e}")
        return False

@app.route('/dashboard')
def dashboard():
    all_trades = Trades.query.order_by(Trades.id.desc()).all()

    # Filtering logic
    apple_trades = [t for t in all_trades if t.apples != 0 and t.monies != 0 and t.juices == 0]
    juice_trades = [t for t in all_trades if t.juices != 0 and t.monies != 0 and t.apples == 0]

    dashboard_html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <meta http-equiv="refresh" content="5">
        <style>
            body { font-family: 'Courier New', Courier, monospace; background: #121212; color: #e0e0e0; }
            .container { display: flex; gap: 200px; padding: 20px; justify-content: center; }
            .column { flex: 1; max-width: 500px; }
            table { width: 100%; border-collapse: collapse; background: #1e1e1e; table-layout: fixed; }
            th, td { padding: 12px 8px; text-align: right; border-bottom: 1px solid #333; }

            /* Header Styling */
            th { color: #888; font-size: 0.75rem; text-transform: uppercase; }
            .col-arrow { width: 50px; text-align: center; }
            .col-price { width: 100px; }
            .col-size { width: 100px; }

            /* Color and Arrow Logic */
            .buy { color: #00ff88; }
            .sell { color: #ff4d4d; }

            .big-arrow { 
                font-size: 4rem; 
                font-weight: bold; 
                display: block;
                text-align: center;
            }

            h1, h2 { text-align: center; color: #ffffff; margin-bottom: 10px; }
            .price-cell { font-weight: bold; font-size: 1.2rem; }
            .size-cell { font-weight: bold; font-size: 1.2rem; }
        </style>
    </head>
    <body>
        <h1>Market Tape</h1>
        <div class="container">

            <div class="column">
                <h2>🍎 Apples</h2>
                <table>
                    <thead>
                        <tr>
                            <th class="col-arrow">Dir</th>
                            <th class="col-price">Price</th>
                            <th class="col-size">Size</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for t in apple_trades %}
                            {% set is_sell = t.apples < 0 %}
                            {% set price = (t.monies / t.apples) | abs %}
                            <tr class="{{ 'sell' if is_sell else 'buy' }}">
                                <td class="col-arrow">
                                    <span class="big-arrow">{{ '↓' if is_sell else '↑' }}</span>
                                </td>
                                <td class="price-cell">{{ "{:.2f}".format(price) }}</td>
                                <td class="size-cell">{{ "-" if is_sell }}{{ t.apples | abs }}</td>
                            </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>

            <div class="column">
                <h2>🧃 Juices</h2>
                <table>
                    <thead>
                        <tr>
                            <th class="col-arrow">Dir</th>
                            <th class="col-price">Price</th>
                            <th class="col-size">Size</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for t in juice_trades %}
                            {% set is_sell = t.juices < 0 %}
                            {% set price = (t.monies / t.juices) | abs %}
                            <tr class="{{ 'sell' if is_sell else 'buy' }}">
                                <td class="col-arrow">
                                    <span class="big-arrow">{{ '↓' if is_sell else '↑' }}</span>
                                </td>
                                <td class="price-cell">{{ "{:.2f}".format(price) }}</td>
                                <td class="size-cell">{{ "-" if is_sell }}{{ t.juices | abs }}</td>
                            </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>

        </div>
        <div style="text-align: center; margin-top: 30px;">
            <a href="/inputTrade" style="color: #666; text-decoration: none; border: 1px solid #444; padding: 10px 20px; border-radius: 5px;">[ Enter New Trade ]</a>
        </div>
    </body>
    </html>
    '''
    return render_template_string(dashboard_html, apple_trades=apple_trades, juice_trades=juice_trades)


@app.route('/users')
def show_users():
    all_users = Users.query.all()

    users_html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>User Directory</title>
        <style>
            body { font-family: 'Segoe UI', sans-serif; background: #121212; color: #e0e0e0; padding: 40px; }
            .container { max-width: 800px; margin: auto; }
            table { width: 100%; border-collapse: collapse; background: #1e1e1e; border-radius: 8px; overflow: hidden; }
            th, td { padding: 15px; text-align: left; border-bottom: 1px solid #333; }
            th { background: #252525; color: #888; text-transform: uppercase; font-size: 0.8rem; }
            tr:hover { background: #2a2a2a; }
            .money { color: #00ff88; font-family: monospace; }
            .apples { color: #ff4d4d; }
            .juice { color: #ffa500; }
            .username { font-weight: bold; color: #fff; }
            h1 { text-align: center; }
            .back-link { display: block; text-align: center; margin-top: 20px; color: #666; text-decoration: none; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>User Balances</h1>
            <table>
                <thead>
                    <tr>
                        <th>Username</th>
                        <th>🍎 Apples</th>
                        <th>🧃 Juice</th>
                        <th>💰 Money</th>
                    </tr>
                </thead>
                <tbody>
                    {% for user in users %}
                    <tr>
                        <td class="username">{{ user.username }}</td>
                        <td class="apples">{{ user.apples }}</td>
                        <td class="juice">{{ user.juices }}</td>
                        <td class="money">${{ "{:,.2f}".format(user.monies) if user.monies else "0.00" }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            <a href="/dashboard" class="back-link">← Back to Dashboard</a>
        </div>
    </body>
    </html>
    '''
    return render_template_string(users_html, users=all_users)




def validate_role(user, delta_apples, delta_juices, delta_monies, capacity):
    """
    Checks if the proposed changes would result in negative balances.
    Returns error message if invalid, else None.
    """
    if user.username.startswith("F") and (delta_apples > 0 or delta_juices != 0):
        return f"User {user.username} can only sell apples."

    if user.username.startswith("A") and delta_juices != 0:
        return f"User {user.username} can only trade apples."

    if user.username.startswith("J") and delta_apples != 0:
        return f"User {user.username} can only trade juice."

    if user.username.startswith("P") and (delta_apples < 0 or delta_juices > 0):
        return f"User {user.username} can only buy apple and sell juice."

    if user.username.startswith("P") and (user.apples + delta_apples + user.juices + delta_juices > capacity):
        return f"User {user.username} out of capacity sell some juice"

    if user.username.startswith("C") and (delta_apples < 0 or delta_juices < 0):
        return f"User {user.username} can only buy apple and buy juice."

    if (user.apples + delta_apples) < 0:
        return f"User {user.username} has insufficient apples."

    if (user.juices + delta_juices) < 0:
        return f"User {user.username} has insufficient juices."

    if (user.monies + delta_monies) < 0:
        return f"User {user.username} has insufficient funds."

    return None

@app.route('/inputTrade', methods=['GET', 'POST'])
def input_trade():
    if request.method == 'POST':
        trade_type = request.form.get('trade_type')
        name_a = request.form.get('partyA')
        name_b = request.form.get('partyB')

        try:
            t_offset = int(request.form.get('timeOffset') or 0)
            price = int(request.form.get('price') or 0)
            volume = int(request.form.get('volume') or 0)

            if price <= 0:
                flash("Error: Price must be positive.", "error")
                return redirect('/inputTrade')
            if volume == 0:
                flash("Error: Volume cannot be zero.", "error")
                return redirect('/inputTrade')

            money_total = price * volume
            dA, dJ = (volume, 0) if trade_type == 'apple' else (0, volume)

            user_a = Users.query.filter_by(username=name_a).first()
            user_b = Users.query.filter_by(username=name_b).first()

            if not user_a or not user_b:
                flash("Error: One or both users not found.", "error")
                return redirect('/inputTrade')

            if user_a.username[0] in ('A', 'J'):
                flash(f"Error: {user_a.username} is a market maker and must always be Party B.", "error")
                return redirect('/inputTrade')

            if user_b.username[0] not in ('A', 'J'):
                flash(f"Error: {user_b.username} is not a market maker — Party B must be an Apple Maker (A) or Juice Maker (J).", "error")
                return redirect('/inputTrade')

            # --- Validation Logic (Assuming you kept the logic from previous steps) ---
            state = GameState.query.first()
            current_limit = state.producer_limit if state else 100

            now = datetime.now()
            current_game_minute = 0
            if state and state.is_active and state.start_time:
                current_game_minute = int((now - state.start_time).total_seconds() // 60)

            # For late farmer apple sales, include discarded apples in validation
            is_late_farmer_apple_sale = (
                user_a.username.startswith("F") and
                trade_type == 'apple' and
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

            error_a = validate_role(user_a, dA, dJ, -money_total, current_limit)

            if is_late_farmer_apple_sale:
                user_a.apples = (user_a.apples or 0) - discard_apples  # restore

            if error_a:
                flash(error_a, "error")
                return redirect('/inputTrade')

            # Party B: Loses apples/juice, Gains money
            error_b = validate_role(user_b, -dA, -dJ, money_total, current_limit)
            if error_b:
                flash(error_b, "error")
                return redirect('/inputTrade')

            # If everything passes:
            if is_late_farmer_apple_sale and discard_apples > 0:
                absorbed = min(discard_apples, -dA)
                farmer_discard_record.apples -= absorbed
                user_a.apples = (user_a.apples or 0) + dA + absorbed
            else:
                user_a.apples += dA
            user_b.apples -= dA
            user_a.juices += dJ
            user_b.juices -= dJ
            user_a.monies -= money_total
            user_b.monies += money_total

            new_trade = Trades(
                partyA=user_a.id,
                partyB=user_b.id,
                apples=dA,
                juices=dJ,
                monies=-money_total,
                timeOffset=t_offset
            )
            db.session.add(new_trade)
            db.session.commit()

            if current_game_minute > t_offset and user_a.username.startswith("P"):
                # 1. Try to find an existing record for this party at this specific time
                existing_update = ProducerUpdates.query.filter_by(
                    party=user_a.id,
                    timeOffset=t_offset + 1
                ).first()

                used = existing_update.apples if existing_update else 0

                # 2. Calculate conversion
                production_limit = state.production_rate if state else 50
                total = min(used + dA, production_limit)
                convert = total - used

                # 3. Apply changes to user
                user_a.apples -= convert
                user_a.juices += convert

                if existing_update:
                    # UPDATE: Modify the existing row
                    existing_update.apples = used + convert
                else:
                    # INSERT: Create a brand new row
                    new_row = ProducerUpdates(
                        party=user_a.id,
                        timeOffset=t_offset + 1,
                        apples=used + convert
                    )
                    db.session.add(new_row)

                # 4. Commit all changes (including user balance updates)
                db.session.commit()

            # The Summary Message
            resource = "🍎 Apples" if trade_type == 'apple' else "🧃 Juices"
            if volume > 0:
                 summary = f"Trade Executed: {name_a} bought {abs(volume)} {resource} from {name_b} at ${price:.2f} (Total: ${abs(money_total):.2f}) at T+{t_offset}m"
            else:
                summary = f"Trade Executed: {name_a} sold {abs(volume)} {resource} to {name_b} at ${price:.2f} (Total: ${abs(money_total):.2f}) at T+{t_offset}m"
            flash(summary, "success")

            if trade_type == 'apple':
                return redirect('/inputTrade?focus=apple')
            return redirect('/inputTrade?focus=juice')


        except Exception as e:
            db.session.rollback()
            flash(f"System Error: {str(e)}", "error")
            return redirect('/inputTrade')

    # Get the current minute for the auto-fill
    state = GameState.query.first()
    current_minute = 0
    if state and state.is_active and state.start_time:
        current_minute = int((datetime.now() - state.start_time).total_seconds() // 60)

    return render_template_string('''
        <style>
            body { font-family: sans-serif; background: #121212; color: #e0e0e0; }
            .container { display: flex; gap: 50px; padding: 20px; justify-content: center; }
            .box { flex: 1; max-width: 400px; border: 2px solid #ccc; padding: 20px; border-radius: 10px; }
            .apple-box { border-color: #ff4d4d; background: #1a1010; }
            .juice-box { border-color: #ffa500; background: #1a1610; }
            input { width: 100%; margin-bottom: 10px; padding: 8px; box-sizing: border-box; background: #2d2d2d; color: white; border: 1px solid #444; }
            button { width: 100%; padding: 12px; cursor: pointer; font-weight: bold; border: none; border-radius: 5px; }

            .flash-container { max-width: 850px; margin: 20px auto; }
            .flash { padding: 15px; border-radius: 5px; margin-bottom: 10px; text-align: center; font-weight: bold; }
            .flash-success { background: #004d26; color: #00ff88; border: 1px solid #00ff88; }
            .flash-error { background: #4d0000; color: #ff4d4d; border: 1px solid #ff4d4d; }
            label { font-size: 0.8rem; color: #aaa; }
        </style>

        <div class="flash-container">
            {% with messages = get_flashed_messages(with_categories=true) %}
              {% if messages %}
                {% for category, message in messages %}
                  <div class="flash flash-{{ category }}">{{ message }}</div>
                {% endfor %}
              {% endif %}
            {% endwith %}
        </div>

        <h1 style="text-align:center">Trading Floor</h1>
        <div class="container">
            <div class="box apple-box">
                <h2>🍎 Apple Trade</h2>
                <form method="POST">
                    <input type="hidden" name="trade_type" value="apple">
                    <label>Taker (Party A)</label>
                    <input type="text" name="partyA" id="partyA_apple" placeholder="Username" required>
                    <label>Market Maker (Party B)</label>
                    <input type="text" name="partyB" placeholder="Username" required>
                    <label>Minute Offset</label>
                    <input type="number" name="timeOffset" value="{{ current_minute }}">
                    <label>Price</label>
                    <input type="number" step="any" name="price" required>
                    <label>Volume</label>
                    <input type="number" step="any" name="volume" required>
                    <button type="submit" style="background: #ff4d4d; color: white;">Execute Apple Trade</button>
                </form>
            </div>

            <div class="box juice-box">
                <h2>🧃 Juice Trade</h2>
                <form method="POST">
                    <input type="hidden" name="trade_type" value="juice">
                    <label>Taker (Party A)</label>
                    <input type="text" name="partyA" id="partyA_juice" placeholder="Username" required>
                    <label>Market Maker (Party B)</label>
                    <input type="text" name="partyB" placeholder="Username" required>
                    <label>Minute Offset</label>
                    <input type="number" name="timeOffset" value="{{ current_minute }}">
                    <label>Price</label>
                    <input type="number" step="any" name="price" required>
                    <label>Volume</label>
                    <input type="number" step="any" name="volume" required>
                    <button type="submit" style="background: #ffa500; color: white;">Execute Juice Trade</button>
                </form>
            </div>
        </div>
        
        <script>
            // Check the URL for the "focus" parameter
            const urlParams = new URLSearchParams(window.location.search);
            const focusTarget = urlParams.get('focus');

            if (focusTarget === 'apple') {
                document.getElementById('partyA_apple').focus();
            } else if (focusTarget === 'juice') {
                document.getElementById('partyA_juice').focus();
            }
        </script>
        
        <p style="text-align: center;"><a href="/dashboard" style="color: #666;">View Live Dashboard</a></p>
    ''', current_minute=current_minute)


@app.route('/schedule')
def show_schedule():
    # We join with Users so we can display the name 'F1' instead of ID '1'
    updates = db.session.query(MinuteUpdates, Users).join(Users, MinuteUpdates.party == Users.id).order_by(
        MinuteUpdates.timeOffset).all()

    schedule_html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Minute Update Schedule</title>
        <style>
            body { font-family: 'Segoe UI', sans-serif; background: #121212; color: #e0e0e0; padding: 40px; }
            .container { max-width: 900px; margin: auto; }
            table { width: 100%; border-collapse: collapse; background: #1e1e1e; border-radius: 8px; overflow: hidden; }
            th, td { padding: 12px; text-align: left; border-bottom: 1px solid #333; }
            th { background: #252525; color: #888; text-transform: uppercase; font-size: 0.75rem; }
            .offset { color: #007bff; font-weight: bold; }
            .plus { color: #00ff88; }
            .minus { color: #ff4d4d; }
            h1 { text-align: center; }
            .nav { text-align: center; margin-bottom: 20px; }
            .nav a { color: #888; text-decoration: none; margin: 0 15px; border: 1px solid #444; padding: 5px 15px; border-radius: 4px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Ledger: Minute Updates</h1>
            <div class="nav">
                <a href="/dashboard">Dashboard</a>
                <a href="/users">Users</a>
                <a href="/admin">Admin</a>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Minute (Offset)</th>
                        <th>User</th>
                        <th>🍎 Apples</th>
                        <th>🧃 Juices</th>
                        <th>💰 Monies</th>
                    </tr>
                </thead>
                <tbody>
                    {% for update, user in updates %}
                    <tr>
                        <td class="offset">T + {{ update.timeOffset }}m</td>
                        <td><strong>{{ user.username }}</strong></td>
                        <td class="{{ 'plus' if update.apples > 0 else 'minus' if update.apples < 0 }}">
                            {{ "+" if update.apples > 0 }}{{ update.apples or 0 }}
                        </td>
                        <td class="{{ 'plus' if update.juices > 0 else 'minus' if update.juices < 0 }}">
                            {{ "+" if update.juices > 0 }}{{ update.juices or 0 }}
                        </td>
                        <td class="{{ 'plus' if update.monies > 0 else 'minus' if update.monies < 0 }}">
                            {{ "+" if update.monies > 0 }}{{ update.monies or 0 }}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    '''
    return render_template_string(schedule_html, updates=updates)

def generateFarmer(id, l):
    for index, item in enumerate(l):
        update = MinuteUpdates(party = id, timeOffset = index, apples = item)
        db.session.add(update)

def generateConsumer(id, l):
    for index, item in enumerate(l):
        update = MinuteUpdates(party = id, timeOffset = index, apples = item[0], juices = item[1])
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
        [[0,40],[0,50], [40,0],[20,0], [0,80],[0,60], [10,10], [20,0],[40,120], [0,150],[0,10],[10,10], [0,70],[50,0],[10,40]],
        [[0,50],[0,40], [20,0],[40,0], [0,60],[0,80], [10,10], [40,0],[20,120], [0,140],[0,20],[10,10],  [0,60],[30,10],[30,40]],

        [[0,50],[0,40], [0,60],[0,80], [20,0],[40,0], [10,10], [20,120],[40,0], [0,150],[0,10],[10,10], [10,50],[0,50],[50,10]],
        [[0,40],[0,50], [0,80],[0,60], [40,0],[20,0], [10,10], [40,120],[20,0], [0,140],[0,20],[10,10], [50,0],[10,80], [10,30]],
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


@app.route('/consumer-targets')
def consumer_targets():
    state = GameState.query.first()

    # 1. Calculate the current game minute
    current_minute = 0
    if state and state.is_active and state.start_time:
        total_seconds = (datetime.now() - state.start_time).total_seconds()
        current_minute = int(total_seconds // 60)

    # 2. Filter for Consumers (C) and the Current Minute
    targets = db.session.query(MinuteUpdates, Users).join(
        Users, MinuteUpdates.party == Users.id
    ).filter(
        Users.username.startswith('C'),
        MinuteUpdates.timeOffset == current_minute
    ).all()

    targets_html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Live Consumer Targets</title>
        <meta http-equiv="refresh" content="5">
        <style>
            body { font-family: 'Segoe UI', sans-serif; background: #0a0a0a; color: #e0e0e0; padding: 40px; text-align: center; }
            .container { max-width: 600px; margin: auto; }
            .clock-box { background: #1e1e1e; padding: 15px; border-radius: 8px; border: 1px solid #007bff; margin-bottom: 20px; }
            .minute-display { font-size: 2rem; color: #007bff; font-weight: bold; }
            table { width: 100%; border-collapse: collapse; background: #151515; border-radius: 8px; overflow: hidden; margin-top: 20px; }
            th, td { padding: 15px; text-align: left; border-bottom: 1px solid #222; }
            th { background: #202020; color: #888; text-transform: uppercase; font-size: 0.75rem; letter-spacing: 1px; }
            .user { color: #fff; font-weight: bold; }
            .val { font-family: 'Courier New', monospace; font-weight: bold; font-size: 1.1rem; }
            .apple { color: #ff4d4d; }
            .juice { color: #ffa500; }
            .empty-state { padding: 40px; color: #666; font-style: italic; }
            .status-tag { font-size: 0.8rem; padding: 4px 8px; border-radius: 4px; background: #222; margin-top: 10px; display: inline-block; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Current Minute Targets</h1>

            <div class="clock-box">
                <div style="font-size: 0.8rem; color: #888;">GAME CLOCK</div>
                <div class="minute-display">T + {{ current_minute }}m</div>
                <div class="status-tag" style="color: {{ '#00ff88' if is_active else '#ff4d4d' }}">
                    ● {{ "GAME ACTIVE" if is_active else "GAME PAUSED" }}
                </div>
            </div>

            {% if targets %}
            <table>
                <thead>
                    <tr>
                        <th>Consumer</th>
                        <th>🍎 Apples</th>
                        <th>🧃 Juices</th>
                    </tr>
                </thead>
                <tbody>
                    {% for update, user in targets %}
                    <tr>
                        <td class="user">{{ user.username }}</td>
                        <td class="val apple">{{ update.apples if update.apples else 0 }}</td>
                        <td class="val juice">{{ update.juices if update.juices else 0 }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <div class="empty-state">
                No consumer targets scheduled for this minute.
            </div>
            {% endif %}

            <div style="margin-top: 30px;">
                <a href="/dashboard" style="color: #444; text-decoration: none;">← Return to Dashboard</a>
            </div>
        </div>
    </body>
    </html>
    '''
    return render_template_string(
        targets_html,
        targets=targets,
        current_minute=current_minute,
        is_active=(state.is_active if state else False)
    )


@app.route('/results')
def results():
    users = Users.query.all()
    user_map = {u.id: u.username for u in users}
    all_updates = MinuteUpdates.query.all()
    all_trades = Trades.query.all()

    results_data = {
        'Farmers (F)': [],
        'AppleMakers (A)': [],
        'Producers (P)': [],
        'JuiceMakers (J)': [],
        'Consumers (C)': []
    }

    for u in users:
        prefix = u.username[0]
        category = {
            'F': 'Farmers (F)',
            'A': 'AppleMakers (A)',
            'P': 'Producers (P)',
            'J': 'JuiceMakers (J)',
            'C': 'Consumers (C)'
        }.get(prefix)

        if not category: continue

        if prefix != 'C':
            # Standard Ranking for non-consumers
            results_data[category].append({
                'username': u.username,
                'monies': u.monies or 0,
                'apples': u.apples or 0,
                'juices': u.juices or 0
            })
        else:
            # --- Consumer Fulfillment Logic (Capped per minute) ---
            total_possible_points = 0
            total_earned_points = 0

            # Get all minutes where this consumer had a target
            updates = MinuteUpdates.query.filter_by(party=u.id).all()

            for up in updates:
                m = up.timeOffset
                target_apples = max(0, up.apples or 0)
                target_juices = max(0, up.juices or 0)
                minute_target_total = target_apples + target_juices

                if minute_target_total == 0:
                    continue

                total_possible_points += minute_target_total

                # Find all trades this user did in THIS specific minute
                trades_this_min = Trades.query.filter(
                    ((Trades.partyA == u.id) | (Trades.partyB == u.id)),
                    (Trades.timeOffset == m)
                ).all()

                # Calculate what they actually bought this minute
                bought_apples = 0
                bought_juices = 0
                for tr in trades_this_min:
                    if tr.partyA == u.id:
                        bought_apples += (tr.apples or 0)
                        bought_juices += (tr.juices or 0)
                    else:
                        # PartyB is the Maker (Inverse delta)
                        bought_apples -= (tr.apples or 0)
                        bought_juices -= (tr.juices or 0)

                # Cap the fulfillment: You can't get more than the target per resource
                # and we ensure negative progress isn't possible per your "buy only" rule
                earned_apples = min(max(0, bought_apples), target_apples)
                earned_juices = min(max(0, bought_juices), target_juices)

                total_earned_points += (earned_apples + earned_juices)

            fulfillment = (total_earned_points / total_possible_points * 100) if total_possible_points > 0 else 0

            results_data[category].append({
                'username': u.username,
                'monies': u.monies or 0,
                'fulfillment': round(fulfillment, 2),
                'score': total_earned_points,
                'max_score': total_possible_points
            })

    # Sort the lists
    for key in results_data:
        if key == 'Consumers (C)':
            # Rank 1: Fulfillment % | Rank 2: Final Money
            results_data[key].sort(key=lambda x: (x['fulfillment'], x['monies']), reverse=True)
        else:
            results_data[key].sort(key=lambda x: x['monies'], reverse=True)

    # Helper to get usernames by ID for the highlights
    h = {
        'apple_best_buy': None, 'apple_worst_buy': None,
        'apple_best_sell': None, 'apple_worst_sell': None,
        'apple_big': None,
        'juice_best_buy': None, 'juice_worst_buy': None,
        'juice_best_sell': None, 'juice_worst_sell': None,
        'juice_big': None
    }

    for t in all_trades:
        is_apple = (t.apples != 0 and t.apples is not None)
        res = 'apple' if is_apple else 'juice'
        raw_vol = t.apples if is_apple else t.juices
        if not raw_vol: continue

        abs_vol = abs(raw_vol)
        price = abs(t.monies / raw_vol)

        # 1. Volume Record (Either direction)
        big_key = f"{res}_big"
        if not h[big_key] or abs_vol > abs(h[big_key].apples or h[big_key].juices):
            h[big_key] = t

        # 2. Buy Records (Taker A bought, so raw_vol > 0)
        if raw_vol > 0:
            # Best Buy = Lowest Price
            k_best = f"{res}_best_buy"
            if not h[k_best] or price < abs(h[k_best].monies / (h[k_best].apples or h[k_best].juices)):
                h[k_best] = t
            # Worst Buy = Highest Price
            k_worst = f"{res}_worst_buy"
            if not h[k_worst] or price > abs(h[k_worst].monies / (h[k_worst].apples or h[k_worst].juices)):
                h[k_worst] = t

        # 3. Sell Records (Taker A sold, so raw_vol < 0)
        else:
            # Best Sell = Highest Price
            k_best = f"{res}_best_sell"
            if not h[k_best] or price > abs(h[k_best].monies / (h[k_best].apples or h[k_best].juices)):
                h[k_best] = t
            # Worst Sell = Lowest Price
            k_worst = f"{res}_worst_sell"
            if not h[k_worst] or price < abs(h[k_worst].monies / (h[k_worst].apples or h[k_worst].juices)):
                h[k_worst] = t

    # Template Logic
    # Define the awards we want to display
    awards = [
        ('apple_best_buy', '🍎 Best Apple Buy (Lowest)'),
        ('apple_worst_buy', '🍎 Worst Apple Buy (Highest)'),
        ('apple_best_sell', '🍎 Best Apple Sell (Highest)'),
        ('apple_worst_sell', '🍎 Worst Apple Sell (Lowest)'),
        ('apple_big', '🍎 Largest Apple Trade'),
        ('juice_best_buy', '🧃 Best Juice Buy (Lowest)'),
        ('juice_worst_buy', '🧃 Worst Juice Buy (Highest)'),
        ('juice_best_sell', '🧃 Best Juice Sell (Highest)'),
        ('juice_worst_sell', '🧃 Worst Juice Sell (Lowest)'),
        ('juice_big', '🧃 Largest Juice Trade')
    ]

    results_html = '''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Final Market Results</title>
                <style>
                    body { font-family: 'Segoe UI', sans-serif; background: #0a0a0a; color: #e0e0e0; padding: 20px; }
                    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; margin-bottom: 40px; }
                    .card { background: #161616; padding: 20px; border-radius: 12px; border: 1px solid #222; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
                    h2 { border-bottom: 1px solid #333; padding-bottom: 12px; color: #fff; font-size: 1.1rem; text-transform: uppercase; letter-spacing: 1px; }
                    table { width: 100%; border-collapse: collapse; }
                    th { text-align: left; color: #666; font-size: 0.7rem; text-transform: uppercase; padding: 10px; }
                    td { padding: 12px 10px; border-bottom: 1px solid #1f1f1f; font-size: 0.9rem; }
                    .money { color: #00ff88; font-family: 'Courier New', monospace; }
                    .user-tag { color: #007bff; font-weight: bold; }
                    .val-tag { color: #ffd700; font-weight: bold; font-family: 'Courier New', monospace; }
                    .time-tag { color: #888; font-style: italic; font-size: 0.8rem; }
                    .award-name { color: #aaa; font-weight: bold; font-size: 0.85rem; }
                </style>
            </head>
            <body>
                <h1 style="text-align:center; letter-spacing: 4px; margin-bottom: 40px;">MARKET RECAP</h1>

                <div class="grid">
                    {% for category, players in data.items() %}
                    <div class="card">
                        <h2>{{ category }}</h2>
                        <table>
                            <thead>
                                <tr><th>User</th><th style="text-align:right">Metric</th><th style="text-align:right">Cash</th></tr>
                            </thead>
                            <tbody>
                                {% for p in players %}
                                <tr>
                                    <td>{{ "🏆 " if loop.first }}{{ p.username }}</td>
                                    <td style="text-align:right">{{ p.fulfillment if 'C' in category else p.apples ~ 'A/' ~ p.juices ~ 'J' }}{{ '%' if 'C' in category }}</td>
                                    <td class="money" style="text-align:right">${{ "{:,.2f}".format(p.monies) }}</td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                    {% endfor %}
                </div>

                <div class="card" style="max-width: 1000px; margin: 0 auto; border-color: #ffd700;">
                    <h2 style="color: #ffd700;">🌟 Market Hall of Fame</h2>
                    <table>
                        <thead>
                            <tr>
                                <th>Record</th>
                                <th>Party A (Taker)</th>
                                <th>Party B (Maker)</th>
                                <th style="text-align:right">Price</th>
                                <th style="text-align:right">Volume</th>
                                <th style="text-align:right">Time</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for key, label in awards %}
                            {% set t = h[key] %}
                            {% if t %}
                                {% set is_apple = (t.apples != 0) %}
                                {% set raw_vol = t.apples if is_apple else t.juices %}
                                {% set price = (t.monies / raw_vol) | abs %}
                                
                                <tr>
                                    <td class="award-name">{{ label }}</td>
                                    <td class="user-tag">{{ um[t.partyA] }}</td>
                                    <td class="user-tag">{{ um[t.partyB] }}</td>
                                    <td class="val-tag" style="text-align:right">${{ "{:.2f}".format(price) }}</td>
                                    <td class="val-tag" style="text-align:right; color: {{ '#ff4d4d' if raw_vol < 0 else '#00ff88' }};">
                                        {{ raw_vol | int }}
                                    </td>
                                    <td class="time-tag" style="text-align:right">T + {{ t.timeOffset }}m</td>
                                </tr>
                            {% endif %}
                            {% endfor %}
                        </tbody>
                    </table>
                </div>

                <p style="text-align:center; margin-top:50px;"><a href="/dashboard" style="color:#444; text-decoration:none;">[ RETURN TO DASHBOARD ]</a></p>
            </body>
            </html>
        '''
    return render_template_string(results_html, data=results_data, h=h, um=user_map, awards=awards)


@app.route('/adjust', methods=['GET', 'POST'])
def adjust_user():
    message = ""
    if request.method == 'POST':
        target_username = request.form.get('username')
        user = Users.query.filter_by(username=target_username).first()

        if user:
            try:
                # Get values from form, default to 0 if empty
                d_apples = int(request.form.get('apples') or 0)
                d_juices = int(request.form.get('juices') or 0)
                d_monies = int(request.form.get('monies') or 0)

                # Apply increments
                user.apples = (user.apples or 0) + d_apples
                user.juices = (user.juices or 0) + d_juices
                user.monies = (user.monies or 0) + d_monies

                db.session.commit()
                message = f"Successfully updated {target_username}!"
            except ValueError:
                message = "Error: Please enter valid numbers."
        else:
            message = "User not found."

    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Adjust Balances</title>
        <style>
            body { font-family: sans-serif; background: #121212; color: white; display: flex; justify-content: center; padding-top: 50px; }
            .card { background: #1e1e1e; padding: 30px; border-radius: 8px; border: 1px solid #333; width: 300px; }
            input { width: 100%; padding: 10px; margin: 10px 0; background: #2d2d2d; border: 1px solid #444; color: white; box-sizing: border-box; }
            button { width: 100%; padding: 10px; background: #007bff; color: white; border: none; cursor: pointer; font-weight: bold; }
            .msg { color: #00ff88; text-align: center; margin-bottom: 10px; }
        </style>
    </head>
    <body>
        <div class="card">
            <h2>Adjust User</h2>
            {% if message %}<p class="msg">{{ message }}</p>{% endif %}
            <form method="POST">
                <input type="text" name="username" placeholder="Username (e.g. F1, C0)" required>
                <label>Add Apples:</label>
                <input type="number" name="apples" value="0">
                <label>Add Juice:</label>
                <input type="number" name="juices" value="0">
                <label>Add Money:</label>
                <input type="number" name="monies" value="0">
                <button type="submit">Apply Adjustment</button>
            </form>
            <p style="text-align:center"><a href="/dashboard" style="color:#666;">Dashboard</a></p>
        </div>
    </body>
    </html>
    ''', message=message)


@app.route('/admin', methods=['GET', 'POST'])
def admin():
    message = ""
    state = GameState.query.first()
    if not state:
        state = GameState(is_active=False)
        db.session.add(state)
        db.session.commit()

    if request.method == 'POST':
        action = request.form.get('action')

        # --- New Toggle Logic ---
        if action == 'toggle':
            if not state.is_active:
                state.is_active = True
                # Set start time only if it's the first time starting
                if not state.start_time:
                    state.start_time = datetime.now()
                state.last_tick = datetime.now()
                message = "Game Clock Started!"
                minuteUpdate(0)
            else:
                state.is_active = False
                message = "Game Clock Paused."
            db.session.commit()

        elif action == 'reset':
            db.session.query(Trades).delete()
            db.session.query(MinuteUpdates).delete()
            db.session.query(FarmerDiscards).delete()
            db.session.query(Users).delete()
            state.is_active = False
            state.start_time = None
            state.last_tick = None

            f = int(request.form.get('f_count') or 4)
            a = int(request.form.get('a_count') or 4)
            p = int(request.form.get('p_count') or 4)
            j = int(request.form.get('j_count') or 4)
            c = int(request.form.get('c_count') or 4)

            addUsers(f, a, p, j, c)
            generate_schedule()
            db.session.commit()
            message = "Game Fully Reset."

    # Determine button label and color based on state
    btn_label = "STOP GAME CLOCK" if state.is_active else "START GAME CLOCK"
    btn_class = "btn-stop" if state.is_active else "btn-start"

    admin_html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Control Panel</title>
        <style>
            body {{ font-family: sans-serif; background: #121212; color: white; padding: 40px; text-align: center; }}
            .card {{ background: #1e1e1e; padding: 20px; border-radius: 8px; border: 1px solid #333; 
                    display: inline-block; min-width: 350px; margin-bottom: 20px; vertical-align: top; }}
            .btn {{ display: block; width: 100%; padding: 12px; margin: 10px 0; border: none; 
                   border-radius: 4px; cursor: pointer; font-weight: bold; text-decoration: none; font-size: 0.9rem; }}
            .btn-start {{ background: #00ff88; color: #000; }}
            .btn-stop {{ background: #ffa500; color: #000; }}
            .btn-reset {{ background: #ff4d4d; color: white; margin-top: 20px; }}

            .input-group {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
            .input-group label {{ font-size: 0.8rem; color: #aaa; }}
            .input-group input {{ width: 50px; background: #333; border: 1px solid #444; color: white; padding: 5px; text-align: center; }}

            .nav-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 20px; }}
            .nav-link {{ background: #333; color: #eee; padding: 10px; text-decoration: none; border-radius: 4px; font-size: 0.8rem; border: 1px solid #444; }}
        </style>
    </head>
    <body>
        <h1>Admin Control Panel</h1>
        {{% if msg %}}<p style="color: #00ff88;">{{{{ msg }}}}</p>{{% endif %}}

        <div class="card">
            <h2>Game Status</h2>
            <form method="POST">
                <button type="submit" name="action" value="toggle" class="btn {btn_class}">{btn_label}</button>
            </form>
            <p style="font-size: 0.8rem; color: #666;">
                Status: <strong>{"ACTIVE" if state.is_active else "PAUSED"}</strong>
            </p>
        </div>

        <div class="card">
            <h2>Initialize Game</h2>
            <form method="POST">
                <div class="input-group"><label>Farmers (F)</label><input type="number" name="f_count" value="4"></div>
                <div class="input-group"><label>AppleMakers (A)</label><input type="number" name="a_count" value="4"></div>
                <div class="input-group"><label>Producers (P)</label><input type="number" name="p_count" value="4"></div>
                <div class="input-group"><label>JuiceMakers (J)</label><input type="number" name="j_count" value="4"></div>
                <div class="input-group"><label>Consumers (C)</label><input type="number" name="c_count" value="4"></div>
                <button type="submit" name="action" value="reset" class="btn btn-reset" 
                        onclick="return confirm('DANGER: This will delete ALL trades. Proceed?')">
                    WIPE & RESET GAME
                </button>
            </form>
        </div>

        <br>

        <div class="card" style="min-width: 720px;">
            <div class="nav-grid">
                <a href="/" class="nav-link">Home</a>
                <a href="/dashboard" class="nav-link">Dashboard</a>
                <a href="/inputTrade" class="nav-link">Trade Floor</a>
                <a href="/users" class="nav-link">User List</a>
                <a href="/consumer-targets" class="nav-link">Live Targets</a>
                <a href="/adjust" class="nav-link">Adjust Balances</a>
                <a href="/results" class="nav-link">Final Results</a>
                <a href="/schedule" class="nav-link">Ledger</a>
            </div>
        </div>
    </body>
    </html>
    '''
    return render_template_string(admin_html, msg=message)


@app.route('/toggle_game', methods=['POST'])
def toggle_game():
    state = GameState.query.first()

    # If no state exists yet, create the singleton row
    if not state:
        state = GameState(is_active=False)
        db.session.add(state)
        db.session.commit()  # Commit here to ensure it exists before we modify it
        state = GameState.query.first()

    if not state.is_active:
        # STARTING THE GAME
        state.is_active = True
        state.start_time = datetime.now()
        state.last_tick = state.start_time
        db.session.commit()
        minuteUpdate(0)
    else:
        # STOPPING THE GAME
        state.is_active = False

    db.session.commit()
    return redirect('/admin')

@app.route('/update_config', methods=['POST'])
def update_config():
    state = GameState.query.first()
    if state:
        new_rate = request.form.get('production_rate')
        new_limit = request.form.get('producer_limit')
        if new_rate:
            state.production_rate = int(new_rate)
        if new_limit:
            state.producer_limit = int(new_limit)
        db.session.commit()
    return redirect('/admin')

# This block only runs if you execute the script directly (python app.py)
if __name__ == '__main__':
    # '0.0.0.0' makes it accessible on your local network
    app.run(host='0.0.0.0', port=5000, debug=True)
