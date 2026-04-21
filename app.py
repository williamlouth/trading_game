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

class GameState(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    start_time = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=False)
    last_tick = db.Column(db.DateTime, nullable=True) # Last time resources were given
    production_rate = db.Column(db.Integer, default=50 )

with app.app_context():
    db.create_all()
    print("Database and tables created")

# Define a "route" (the URL path) and the function that handles it

def minuteUpdate():
    users = Users.query.all()
    state = GameState.query.first()
    rate = state.production_rate if state else 50
    
    for user in users:
        if(user.username.startswith("F")):
            user.apples += 50
        if(user.username.startswith("C")):
            user.monies += 5000
        if(user.username.startswith("P")):
            produced = min(user.apples, rate)
            user.apples -= produced
            user.juices += produced

def tick_game():
    state = GameState.query.first()
    if not state or not state.is_active:
        return

    now = datetime.now()
    # Check if 60 seconds have passed since the last distribution
    if state.last_tick is None or now >= state.last_tick + timedelta(seconds=60):
        # Calculate how many 60-second intervals passed (handles lag)
        seconds_passed = (now - (state.last_tick or state.start_time)).total_seconds()
        intervals = int(seconds_passed // 60)

        if intervals > 0:
            minuteUpdate()

            # Update last_tick to exactly the point where we distributed
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
    new_entry = Users(username = name, apples = apples, juices = juices, monies = monies)
    db.session.add(new_entry)
    pass

def addUsers(noFarmers, noAppleMakers, noProducers, noJuiceMakers, noConsumers):
    try:
        for i in range(0,int(noFarmers)):
            addUser("F" + str(i), 0, 0, 0)
        for i in range(0,int(noAppleMakers)):
            addUser("A" + str(i), 0, 0, 500)
        for i in range(0,int(noProducers)):
            addUser("P" + str(i), 0, 0, 100)
        for i in range(0,int(noJuiceMakers)):
            addUser("J" + str(i), 0, 0, 500)
        for i in range(0,int(noConsumers)):
            addUser("C" + str(i), 0, 0, 0)
        db.session.commit()

        return "Success <a href='/admin'>Go back</a>"
    except ValueError:
        return "Please enter valid numbers", 400


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
            # If volume is positive, A is SELLING (giving away goods, receiving money)
            # If volume is negative, A is BUYING (receiving goods, giving away money)
            money_total = price * volume
            dA, dJ = (volume, 0) if trade_type == 'apple' else (0, volume)

        except ValueError:
            return "Invalid numbers entered.", 400

        user_a = Users.query.filter_by(username=name_a).first()
        user_b = Users.query.filter_by(username=name_b).first()

        if not user_a or not user_b:
            return "One or both users not found.", 404

        # --- ROLE-BASED VALIDATION LOGIC ---
        def validate_role(user, delta_apples, delta_juices):
            name = user.username
            is_selling_apple = delta_apples > 0
            is_buying_apple = delta_apples < 0
            is_selling_juice = delta_juices > 0
            is_buying_juice = delta_juices < 0

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
                if (final_apples + final_juice) > 100:
                    return "Producers cannot hold more than 100 total units."

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
        new_a_apples, new_b_apples = user_a.apples - dA, user_b.apples + dA
        new_a_juices, new_b_juices = user_a.juices - dJ, user_b.juices + dJ
        new_a_monies, new_b_monies = user_a.monies + money_total, user_b.monies - money_total

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


@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        # Safely drop and recreate
        db.drop_all()
        db.create_all()
        default_state = GameState(is_active=False)
        db.session.add(default_state)
        # Repopulate
        addUsers(request.form.get('n1'), request.form.get('n2'),
                 request.form.get('n3'), request.form.get('n4'),
                 request.form.get('n5'))
        return redirect('/admin')

    # Get game state from DB instead of a global variable
    state = GameState.query.first()
    is_active = state.is_active if state else False
    current_rate = state.production_rate if state else 50

    status_text = "RUNNING" if is_active else "STOPPED"
    button_text = "Stop Game" if is_active else "Start Game"

    form_html = f'''
            <h1>Admin Control Panel</h1>

            <div style="border: 2px solid #ccc; padding: 15px; margin-bottom: 20px; font-family: sans-serif;">
                <h3>Game Status: <span style="color: {'green' if is_active else 'red'};">{status_text}</span></h3>
                <form action="/toggle_game" method="POST" style="display:inline;">
                    <button type="submit">{button_text}</button>
                </form>

                <hr>

                <form action="/update_config" method="POST">
                    <label>P-User Production Rate (Apples -> Juice): </label>
                    <input type="number" name="production_rate" value="{current_rate}">
                    <button type="submit">Update Rate</button>
                </form>
            </div>

            <form method="POST" style="font-family: sans-serif; border: 1px solid #444; padding: 15px;">
                <h3>Reset & Populate Users</h3>
                <button type="submit" style="background-color: #ff4444; color: white;">RESET DATABASE</button>
            </form>
        '''
    return render_template_string(form_html)


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
        if new_rate:
            state.production_rate = int(new_rate)
            db.session.commit()
    return redirect('/admin')

# This block only runs if you execute the script directly (python app.py)
if __name__ == '__main__':
    # '0.0.0.0' makes it accessible on your local network
    app.run(host='0.0.0.0', port=5000, debug=True)
