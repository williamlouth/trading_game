from flask import Flask, request, render_template_string
import os
from flask_sqlalchemy import SQLAlchemy

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

with app.app_context():
    db.create_all()
    print("Database and tables created")

# Define a "route" (the URL path) and the function that handles it
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


@app.route('/inputTrade', methods=['GET', 'POST'])
def input_trade():
    if request.method == 'POST':
        trade_type = request.form.get('trade_type')
        name_a = request.form.get('partyA')
        name_b = request.form.get('partyB')

        try:
            price = float(request.form.get('price') or 0)
            volume = float(request.form.get('volume') or 0)

            # GUARD: Price must be positive, but volume can be +/-
            if price <= 0:
                return "Price must be a positive number.", 400
            if volume == 0:
                return "Volume cannot be zero.", 400

            # Money moves opposite to the goods
            # If volume is +, A gives item and receives money
            # If volume is -, A receives item and gives money
            money_total = price * volume

            dA, dJ = 0, 0
            if trade_type == 'apple':
                dA = volume
            else:
                dJ = volume

        except ValueError:
            return "Invalid numbers entered.", 400

        user_a = Users.query.filter_by(username=name_a).first()
        user_b = Users.query.filter_by(username=name_b).first()

        if not user_a or not user_b:
            return "One or both users not found.", 404

        # Calculate new balances
        # Subtract dA from user_a (if dA is negative, it adds to user_a)
        new_a_apples, new_b_apples = user_a.apples - dA, user_b.apples + dA
        new_a_juices, new_b_juices = user_a.juices - dJ, user_b.juices + dJ

        # Money logic: user_a receives money_total
        # If money_total is +, user_a balance goes up. If -, it goes down.
        new_a_monies, new_b_monies = user_a.monies + money_total, user_b.monies - money_total

        # CHECK: Nothing Negative
        balances = [new_a_apples, new_a_juices, new_a_monies,
                    new_b_apples, new_b_juices, new_b_monies]

        if any(b < 0 for b in balances):
            return "Trade Rejected: Insufficient funds or stock for this operation.", 400

        try:
            user_a.apples, user_b.apples = new_a_apples, new_b_apples
            user_a.juices, user_b.juices = new_a_juices, new_b_juices
            user_a.monies, user_b.monies = new_a_monies, new_b_monies

            # Record trade in DB
            new_trade = Trades(
                partyA=user_a.id, partyB=user_b.id,
                apples=dA, juices=dJ, monies=-money_total
            )

            db.session.add(new_trade)
            db.session.commit()
            return f"Trade successful! Volume: {volume}, Price: {price} <a href='/inputTrade'>Back</a>"
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
                    <label>Seller (Party A):</label>
                    <input type="text" name="partyA" placeholder="Username" required>
                    <label>Buyer (Party B):</label>
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
                    <label>Seller (Party A):</label>
                    <input type="text" name="partyA" placeholder="Username" required>
                    <label>Buyer (Party B):</label>
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
@app.route('/admin', methods=['GET', 'Post'])
def admin():
    if request.method == 'POST':
        Users.__table__.drop(db.engine)
        db.create_all()
        addUsers(request.form.get('n1'),request.form.get('n2'),request.form.get('n3'),request.form.get('n4'),request.form.get('n5'))

    form_html = '''
    <h1>Admin Data Entry</h1>
    <form method="POST">
        <p>Farmers: <input type="number" step="any" name="n1" required></p>
        <p>AppleMakers: <input type="number" step="any" name="n2" required></p>
        <p>Producers: <input type="number" step="any" name="n3" required></p>
        <p>JuiceMakers: <input type="number" step="any" name="n4" required></p>
        <p>Consumers: <input type="number" step="any" name="n5" required></p>
        <button type="submit">Submit Data</button>
    </form>
    '''
    return render_template_string(form_html)

# This block only runs if you execute the script directly (python app.py)
if __name__ == '__main__':
    # '0.0.0.0' makes it accessible on your local network
    app.run(host='0.0.0.0', port=5000, debug=True)
