from flask import Blueprint, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db
import datetime
from functools import wraps

auth_bp = Blueprint('auth', __name__, template_folder='templates')

def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    db = get_db()
    return db.execute('SELECT id, username, full_name FROM users WHERE id=?', (uid,)).fetchone()

def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for('auth.login'))  
        return f(*args, **kwargs)
    return wrapped

@auth_bp.route('/')
def index():
    user = current_user()
    if user:
        return redirect(url_for('dashboard.dashboard'))  
    return render_template('index.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        full_name = request.form.get('full_name')
        if not username or not password:
            return 'Missing username or password', 400
        db = get_db()
        try:
            db.execute(
                'INSERT INTO users (username, password_hash, full_name, created_at) VALUES (?, ?, ?, ?)',
                (username, generate_password_hash(password), full_name, datetime.datetime.utcnow().isoformat())
            )
            db.commit()
        except:
            return 'Username already exists', 400
        return redirect(url_for('auth.login'))  
    return render_template('register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            return redirect(url_for('dashboard.dashboard'))  
        return 'Invalid credentials', 400
    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.index'))  