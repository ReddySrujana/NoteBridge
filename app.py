from flask import Flask
from flask_socketio import SocketIO
from config import SECRET_KEY, DEBUG
from database import get_db, close_connection, init_db
import os

# Import blueprints
from auth import auth_bp
from dashboard import dashboard_bp
from notebooks import notebook_bp
from groups import group_bp

app = Flask(__name__)
app.config.update(SECRET_KEY=SECRET_KEY, DEBUG=DEBUG)
socketio = SocketIO(app, cors_allowed_origins="*")

# Register Blueprints without prefix so url_for('login') works
app.register_blueprint(auth_bp, url_prefix='')
app.register_blueprint(dashboard_bp, url_prefix='')
app.register_blueprint(notebook_bp, url_prefix='')
app.register_blueprint(group_bp, url_prefix='')

# Close DB after request
app.teardown_appcontext(close_connection)

# Initialize DB if not exists
if not os.path.exists('notebridge.db'):
    with app.app_context():
        init_db(get_db())
        print("Initialized database.")

if __name__ == '__main__':
    print('Starting NoteBridge on http://127.0.0.1:5000')
    socketio.run(app, host='0.0.0.0', port=5000, debug=DEBUG)
