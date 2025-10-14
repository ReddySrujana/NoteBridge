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

# Import Help blueprint
from flask import Blueprint, render_template
from auth import login_required, current_user

help_bp = Blueprint('help', __name__, url_prefix='/help', template_folder='templates')

@help_bp.route('', methods=['GET'])
@login_required
def help_page():
    user = current_user()
    return render_template('help.html', user=user)

app = Flask(__name__)
app.config.update(SECRET_KEY=SECRET_KEY, DEBUG=DEBUG)
socketio = SocketIO(app, cors_allowed_origins="*")

# Register Blueprints
app.register_blueprint(auth_bp, url_prefix='')        # Auth routes
app.register_blueprint(dashboard_bp, url_prefix='')   # Dashboard routes
app.register_blueprint(notebook_bp, url_prefix='')    # Notebook routes
app.register_blueprint(group_bp)                      # Group routes use the prefix defined in groups.py (/groups)
app.register_blueprint(help_bp)                       # Help page

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
