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
        name_a = request.form.get('partyA')
        name_b = request.form.get('partyB')

        try:
            # Net change for Party A
            # Positive = A gives to B | Negative = A receives from B
            dA = int(request.form.get('apples') or 0)
            dJ = int(request.form.get('juices') or 0)
            dM = int(request.form.get('monies') or 0)
        except ValueError:
            return "Invalid numbers. Please enter whole numbers for Integer columns.", 400

        # Fetch users from the 'users' table
        user_a = Users.query.filter_by(username=name_a).first()
        user_b = Users.query.filter_by(username=name_b).first()

        if not user_a or not user_b:
            return "One or both users not found.", 404

        # 1. Validation: Check for "Nothing Negative" before modifying
        if (user_a.apples - dA < 0 or user_a.juices - dJ < 0 or user_a.monies - dM < 0 or
                user_b.apples + dA < 0 or user_b.juices + dJ < 0 or user_b.monies + dM < 0):
            return "Trade Rejected: This would result in a negative balance.", 400

        try:
            # 2. Update the User objects (SQLAlchemy tracks these changes)
            user_a.apples -= dA
            user_a.juices -= dJ
            user_a.monies -= dM

            user_b.apples += dA
            user_b.juices += dJ
            user_b.monies += dM

            # 3. Create the Trade record
            new_trade = Trades(
                partyA=user_a.id,
                partyB=user_b.id,
                apples=dA,
                juices=dJ,
                monies=dM
            )

            # 4. Commit everything to the database
            db.session.add(new_trade)
            db.session.commit()  # This updates BOTH users and inserts the trade

            return f"Trade successful! {name_a} and {name_b} balances updated. <a href='/inputTrade'>New Trade</a>"

        except Exception as e:
            db.session.rollback()
            return f"Database error: {str(e)}", 500

    return render_template_string('''
    <h1>Complex Trade Entry</h1>
    <p>A gives to B (Positive) | A receives from B (Negative)</p>
    <form method="POST">
        <p>Party A (Username): <input type="text" name="partyA" required></p>
        <p>Party B (Username): <input type="text" name="partyB" required></p>
        <hr>
        <p>Apples: <input type="number" name="apples" value="0"></p>
        <p>Juices: <input type="number" name="juices" value="0"></p>
        <p>Monies: <input type="number" name="monies" value="0"></p>
        <button type="submit">Execute Trade</button>
    </form>
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
