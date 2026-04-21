from flask import Flask

# Initialize the Flask application
app = Flask(__name__)

# Define a "route" (the URL path) and the function that handles it
@app.route('/')
def hello_world():
    return 'Hello, World! This is running on my Oracle ARM instance.'

# This block only runs if you execute the script directly (python app.py)
if __name__ == '__main__':
    # '0.0.0.0' makes it accessible on your local network
    app.run(host='0.0.0.0', port=5000, debug=True)
