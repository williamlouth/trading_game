from email.policy import default

from flask import Flask, request, render_template_string, redirect
import os
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta

# Initialize the Flask application
app = Flask(__name__)

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

with app.app_context():
    db.create_all()
    print("Database and tables created")

# Define a "route" (the URL path) and the function that handles it

def minuteUpdate(current_offset):
    # Find all update instructions for this specific minute
    updates = MinuteUpdates.query.filter_by(timeOffset=current_offset).all()

    for update in updates:
        # Find the specific user this update belongs to
        user = Users.query.get(update.party)
        if user:
            # Apply the changes (defaulting to 0 if the column is None)
            user.apples = (user.apples or 0) + (update.apples or 0)
            user.juices = (user.juices or 0) + (update.juices or 0)
            user.monies = (user.monies or 0) + (update.monies or 0)

            # Safety check: Prevent negative balances if needed
            user.apples = max(0, user.apples)
            user.juices = max(0, user.juices)
            user.monies = max(0, user.monies)
    users = Users.query.all()
    state = GameState.query.first()
    rate = state.production_rate if state else 50
    for u in users:
        if u.username.startswith("P"):
            produced = min(u.apples, rate)
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
    if request.endpoint in ['dashboard']:
        tick_game()
@app.route('/')
def hello_world():
    return 'Hello, World! This is running on my Oracle ARM instance.'


def addUser(name, apples, juices, monies):
    # Ensure values are integers to prevent DB errors
    new_entry = Users(
        username=name,
        apples=int(apples or 0),
        juices=int(juices or 0),
        monies=int(monies or 0)
    )
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
            addUser(f"A{i}", 0, 0, 500)
        for i in range(p_count):
            addUser(f"P{i}", 0, 0, 100)
        for i in range(j_count):
            addUser(f"J{i}", 0, 0, 500)
        for i in range(c_count):
            addUser(f"C{i}", 0, 0, 0)

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

@app.route('/inputTrade', methods=['GET', 'POST'])
def input_trade():
    if request.method == 'POST':
        trade_type = request.form.get('trade_type')
        name_a = request.form.get('partyA')
        name_b = request.form.get('partyB')

        try:
            price = float(request.form.get('price') or 0)
            volume = float(request.form.get('volume') or 0)

            if price <= 0: return "Price must be a positive number.", 400
            if volume == 0: return "Volume cannot be zero.", 400

            # dA/dJ interpretation:
            # If volume is positive, A is BUYING
            # If volume is negative, A is SELLING
            money_total = price * volume
            dA, dJ = (volume, 0) if trade_type == 'apple' else (0, volume)

        except ValueError:
            return "Invalid numbers entered.", 400

        user_a = Users.query.filter_by(username=name_a).first()
        user_b = Users.query.filter_by(username=name_b).first()

        if not user_a or not user_b:
            return "One or both users not found.", 404

        # --- ROLE-BASED VALIDATION LOGIC ---
        state = GameState.query.first()
        current_limit = state.producer_limit if state else 100
        def validate_role(user, delta_apples, delta_juices):
            name = user.username
            is_selling_apple = delta_apples < 0
            is_buying_apple = delta_apples > 0
            is_selling_juice = delta_juices < 0
            is_buying_juice = delta_juices > 0

            # Farmer (F): Only sell Apples
            if name.startswith('F'):
                if is_buying_apple or is_buying_juice or is_selling_juice:
                    return "Farmers can only sell apples."

            # Producer (P): Buy Apples, Sell Juice, Max 100 inventory
            elif name.startswith('P'):
                if is_selling_apple or is_buying_juice:
                    return "Producers can only buy apples and sell juice."
                # Post-trade check for P-users
                final_apples = user.apples - delta_apples
                final_juice = user.juices - delta_juices
                if (final_apples + final_juice) > current_limit:
                    return f"Producers cannot hold more than {current_limit} total units."

            # AppleMaker (A): Trade Apples only
            elif name.startswith('A'):
                if is_selling_juice or is_buying_juice:
                    return "AppleMakers can only trade apples."

            # JuiceMaker (J): Trade Juice only
            elif name.startswith('J'):
                if is_selling_apple or is_buying_apple:
                    return "JuiceMakers can only trade juice."

            # Consumer (C): Buy only
            elif name.startswith('C'):
                if is_selling_apple or is_selling_juice:
                    return "Consumers can only buy, not sell."

            return None

        # Validate Party A (The Taker)
        error_a = validate_role(user_a, dA, dJ)
        if error_a: return f"Party A Error: {error_a}", 400

        # Validate Party B (The Maker - direction is inverted)
        error_b = validate_role(user_b, -dA, -dJ)
        if error_b: return f"Party B Error: {error_b}", 400
        # -----------------------------------

        # Calculate new balances
        new_a_apples, new_b_apples = user_a.apples + dA, user_b.apples - dA
        new_a_juices, new_b_juices = user_a.juices + dJ, user_b.juices - dJ
        new_a_monies, new_b_monies = user_a.monies - money_total, user_b.monies + money_total

        # Final Balance Check (Safety Net)
        balances = [new_a_apples, new_a_juices, new_a_monies,
                    new_b_apples, new_b_juices, new_b_monies]

        if any(b < 0 for b in balances):
            return "Trade Rejected: Insufficient funds or stock.", 400

        try:
            user_a.apples, user_b.apples = new_a_apples, new_b_apples
            user_a.juices, user_b.juices = new_a_juices, new_b_juices
            user_a.monies, user_b.monies = new_a_monies, new_b_monies

            new_trade = Trades(partyA=user_a.id, partyB=user_b.id, apples=dA, juices=dJ, monies=-money_total)
            db.session.add(new_trade)
            db.session.commit()
            return f"Trade successful! <a href='/inputTrade'>Back</a>"
        except Exception as e:
            db.session.rollback()
            return f"Error: {str(e)}", 500

    return render_template_string('''
        <style>
            .container { display: flex; gap: 50px; font-family: sans-serif; padding: 20px; }
            .box { flex: 1; border: 2px solid #ccc; padding: 20px; border-radius: 10px; }
            .apple-box { border-color: #ffcccb; background: #fff5f5; }
            .juice-box { border-color: #ffe5b4; background: #fffaf0; }
            input { width: 100%; margin-bottom: 10px; padding: 8px; box-sizing: border-box; }
            button { width: 100%; padding: 10px; cursor: pointer; font-weight: bold; }
        </style>

        <h1>Trading Floor</h1>
        <div class="container">
            <div class="box apple-box">
                <h2>🍎 Apple Trade</h2>
                <form method="POST">
                    <input type="hidden" name="trade_type" value="apple">
                    <label>Taker (Party A):</label>
                    <input type="text" name="partyA" placeholder="Username" required>
                    <label>Market Maker (Party B):</label>
                    <input type="text" name="partyB" placeholder="Username" required>
                    <label>Price (per apple):</label>
                    <input type="number" step="any" name="price" required>
                    <label>Volume (Qty):</label>
                    <input type="number" step="any" name="volume" required>
                    <button type="submit" style="background: #ff4d4d; color: white;">Execute Apple Trade</button>
                </form>
            </div>

            <div class="box juice-box">
                <h2>🧃 Juice Trade</h2>
                <form method="POST">
                    <input type="hidden" name="trade_type" value="juice">
                    <label>Taker (Party A):</label>
                    <input type="text" name="partyA" placeholder="Username" required>
                    <label>Market Maker (Party B):</label>
                    <input type="text" name="partyB" placeholder="Username" required>
                    <label>Price (per juice):</label>
                    <input type="number" step="any" name="price" required>
                    <label>Volume (Qty):</label>
                    <input type="number" step="any" name="volume" required>
                    <button type="submit" style="background: #ffa500; color: white;">Execute Juice Trade</button>
                </form>
            </div>
        </div>
        <p><a href="/dashboard">View Live Dashboard</a></p>
        ''')


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

def generate_schedule():
    users = Users.query.all()
    farmerCount = 0
    farmerLists = [
        [50,70,60,10,10,100,100,50,30,50,20,90,90,60,50],
        [50,70,60,10,10,100,90,50,30,60,20,100,90,50,50],
        [50,60,70,20,10,90,100,50,30,50,10,90,100,60,50],
        [50,60,70,20,10,90,90,50,30,60,10,100,100,50,50]
    ]
    for user in users:
        if user.username.startswith("F"):
            generateFarmer(user.id, farmerLists[farmerCount])
            if farmerCount + 1 < len(farmerLists):
                farmerCount += 1

    db.session.commit()

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        # 1. Wipe everything
        db.drop_all()
        db.create_all()

        # 2. Setup Game State with current or default values
        default_state = GameState(
            is_active=False,
            production_rate=50,
            producer_limit=100
        )
        db.session.add(default_state)

        # 3. Create Users directly from form data
        try:
            counts = {
                'F': int(request.form.get('n1') or 0),
                'A': int(request.form.get('n2') or 0),
                'P': int(request.form.get('n3') or 0),
                'J': int(request.form.get('n4') or 0),
                'C': int(request.form.get('n5') or 0)
            }

            for prefix, count in counts.items():
                for i in range(count):
                    name = f"{prefix}{i}"
                    a, j, m = 0, 0, 0
                    if prefix == 'A': m = 500
                    if prefix == 'P': m = 100
                    if prefix == 'J': m = 500
                    addUser(name, a, j, m)

            db.session.commit()
            print("Database reset and users created successfully.")
            print("F", counts['F'])
            print("A", counts['A'])
            print("P", counts['P'])
            print("J", counts['J'])
            print("C", counts['C'])

            generate_schedule()
        except Exception as e:
            db.session.rollback()
            print(f"Error during reset: {e}")
            return f"Database Error: {e}", 500

        return redirect('/admin')

    # GET logic
    state = GameState.query.first()
    if not state:
        state = GameState(is_active=False, production_rate=50, producer_limit=100)
        db.session.add(state)
        db.session.commit()

    status_text = "RUNNING" if state.is_active else "STOPPED"
    status_color = "#00ff88" if state.is_active else "#ff4d4d"
    button_text = "Stop Game" if state.is_active else "Start Game"

    admin_html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Control Panel</title>
        <style>
            body {{ font-family: 'Segoe UI', sans-serif; background: #121212; color: #e0e0e0; padding: 20px; }}
            .card {{ background: #1e1e1e; padding: 20px; border-radius: 8px; margin-bottom: 20px; border: 1px solid #333; max-width: 500px; margin: auto; }}
            h2 {{ margin-top: 0; color: #fff; border-bottom: 1px solid #333; padding-bottom: 10px; }}
            label {{ display: block; margin: 10px 0 5px; font-size: 0.85rem; color: #bbb; }}
            input {{ width: 100%; padding: 8px; background: #2d2d2d; border: 1px solid #444; color: white; border-radius: 4px; box-sizing: border-box; }}
            button {{ padding: 10px 15px; cursor: pointer; border: none; border-radius: 4px; font-weight: bold; margin-top: 10px; }}
            .btn-blue {{ background: #007bff; color: white; }}
            .btn-green {{ background: #28a745; color: white; }}
            .btn-red {{ background: #dc3545; color: white; width: 100%; padding: 15px; }}
            .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h2>Game Engine</h2>
            <p>Status: <span style="color: {status_color}">{status_text}</span></p>
            <form action="/toggle_game" method="POST">
                <button type="submit" class="btn-blue">{button_text}</button>
            </form>
        </div>

        <div class="card">
            <h2>Economic Parameters</h2>
            <form action="/update_config" method="POST">
                <label>Production Rate (Apples → Juice)</label>
                <input type="number" name="production_rate" value="{state.production_rate}">
                <label>P-User Inventory Limit</label>
                <input type="number" name="producer_limit" value="{state.producer_limit}">
                <button type="submit" class="btn-green">Update Settings</button>
            </form>
        </div>

        <div class="card" style="border-color: #dc3545;">
            <h2 style="color: #dc3545;">Reset World</h2>
            <form method="POST">
                <div class="grid">
                    <div><label>Farmers</label><input type="number" name="n1" value="5"></div>
                    <div><label>AppleMakers</label><input type="number" name="n2" value="3"></div>
                    <div><label>Producers</label><input type="number" name="n3" value="2"></div>
                    <div><label>JuiceMakers</label><input type="number" name="n4" value="3"></div>
                    <div><label>Consumers</label><input type="number" name="n5" value="10"></div>
                </div>
                <button type="submit" class="btn-red" onclick="return confirm('Are you sure')">WIPE & RECREATE USERS</button>
            </form>
        </div>
        <p style="text-align:center"><a href="/dashboard" style="color:#666; text-decoration:none;">Dashboard</a></p>
    </body>
    </html>
    '''
    return render_template_string(admin_html)


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
