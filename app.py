from flask import Flask, request, render_template_string
import os
from flask_sqlalchemy import SQLAlchemy

# Initialize the Flask application
app = Flask(__name__)

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'sqlite.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    apples = db.Column(db.Float, nullable=True)
    juices = db.Column(db.Float, nullable=True)
    monies = db.Column(db.Float, nullable=True)

with app.app_context():
    db.create_all()
    print("Database and tables created")

# Define a "route" (the URL path) and the function that handles it
@app.route('/')
def hello_world():
    return 'Hello, World! This is running on my Oracle ARM instance.'

def addUser(name, apples, juices, monies):
    new_entry = User(username = name, apples = apples, juices = juices, monies = monies)
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

@app.route('/admin', methods=['GET', 'Post'])
def admin():
    if request.method == 'POST':
        User.__table__.drop(db.engine)
        db.create_all()
        addUsers(request.form.get('n1'),request.form.get('n2'),request.form.get('n3'),request.form.get('n4'),request.form.get('n5'))

    form_html = '''
    <h1>Admin Data Entry</h1>
    <form method="POST">
        <p>Value 1: <input type="number" step="any" name="n1" required></p>
        <p>Value 2: <input type="number" step="any" name="n2" required></p>
        <p>Value 3: <input type="number" step="any" name="n3" required></p>
        <p>Value 4: <input type="number" step="any" name="n4" required></p>
        <p>Value 5: <input type="number" step="any" name="n5" required></p>
        <button type="submit">Submit Data</button>
    </form>
    '''
    return render_template_string(form_html)

# This block only runs if you execute the script directly (python app.py)
if __name__ == '__main__':
    # '0.0.0.0' makes it accessible on your local network
    app.run(host='0.0.0.0', port=5000, debug=True)
