<<<<<<< HEAD
<<<<<<< HEAD
from flask import Flask, g, render_template, request, redirect, url_for, session, jsonify, abort
from werkzeug.security import generate_password_hash, check_password_hash
from flask_socketio import SocketIO, join_room, leave_room, emit
import sqlite3
import os
import datetime

# ---------- Configuration ----------
DATABASE = os.path.join(os.path.dirname(__file__), 'notebridge.db')
SECRET_KEY = os.environ.get('SECRET_KEY', 'qwerty1234')
DEBUG = True

# ---------- Flask App Setup ----------
app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config.update(SECRET_KEY=SECRET_KEY, DEBUG=DEBUG)
socketio = SocketIO(app, cors_allowed_origins="*")

# ---------- Database Utilities ----------
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    schema = """
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS group_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        role TEXT DEFAULT 'member',
        joined_at TEXT NOT NULL,
        FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS notebooks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        created_at TEXT NOT NULL,
        is_shared INTEGER DEFAULT 0,
        FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        notebook_id INTEGER NOT NULL,
        title TEXT,
        content TEXT,
        created_by INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT,
        FOREIGN KEY(notebook_id) REFERENCES notebooks(id) ON DELETE CASCADE,
        FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS contributions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        note_id INTEGER NOT NULL,
        user_id INTEGER,
        action TEXT,
        timestamp TEXT NOT NULL,
        detail TEXT,
        FOREIGN KEY(note_id) REFERENCES notes(id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        note_id INTEGER NOT NULL,
        tag TEXT NOT NULL,
        FOREIGN KEY(note_id) REFERENCES notes(id) ON DELETE CASCADE
    );
    """
    db = get_db()
    db.executescript(schema)
    db.commit()

if not os.path.exists(DATABASE):
    with app.app_context():
        init_db()
        print('Initialized database at', DATABASE)

# ---------- Authentication Helpers ----------
def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    db = get_db()
    user = db.execute('SELECT id, username, full_name, created_at FROM users WHERE id=?', (uid,)).fetchone()
    return user

def login_required(f):
    from functools import wraps
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return wrapped

# ---------- Auth Routes ----------
@app.route('/')
def index():
    user = current_user()
    if user:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        full_name = request.form.get('full_name')
        if not username or not password:
            return 'Missing username or password', 400
        db = get_db()
        try:
            db.execute('INSERT INTO users (username, password_hash, full_name, created_at) VALUES (?, ?, ?, ?)',
                       (username, generate_password_hash(password), full_name, datetime.datetime.utcnow().isoformat()))
            db.commit()
        except sqlite3.IntegrityError:
            return 'Username already exists', 400
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            return redirect(url_for('dashboard'))
        return 'Invalid credentials', 400
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ---------- Dashboard ----------
@app.route('/dashboard')
@login_required
def dashboard():
    user = current_user()
    db = get_db()
    notebooks = db.execute('SELECT * FROM notebooks WHERE owner_id=?', (user['id'],)).fetchall()
    shared_notebooks = db.execute(
        'SELECT n.* FROM notebooks n '
        'JOIN group_members gm ON gm.user_id=? '
        'JOIN groups g ON g.id=gm.group_id '
        'WHERE n.is_shared=1', 
        (user['id'],)
    ).fetchall()
    groups = db.execute(
        'SELECT g.*, (SELECT COUNT(*) FROM group_members gm WHERE gm.group_id=g.id) AS members FROM groups g'
    ).fetchall()
    return render_template('dashboard.html', user=user, notebooks=notebooks, shared_notebooks=shared_notebooks, groups=groups)

# ---------- Notebook Routes ----------
@app.route('/notebook/<int:notebook_id>')
@login_required
def view_notebook(notebook_id):
    db = get_db()
    nb = db.execute('SELECT * FROM notebooks WHERE id=?', (notebook_id,)).fetchone()
    if not nb:
        abort(404)
    notes = db.execute('SELECT * FROM notes WHERE notebook_id=? ORDER BY updated_at DESC NULLS LAST, created_at DESC', (notebook_id,)).fetchall()
    return render_template('notebook.html', notebook=nb, notes=notes)

@app.route('/notebook/create', methods=['POST'])
@login_required
def create_notebook():
    title = request.form.get('title') or 'Untitled Notebook'
    is_shared = 1 if request.form.get('is_shared') else 0
    user = current_user()
    now = datetime.datetime.utcnow().isoformat()
    db = get_db()
    db.execute(
        'INSERT INTO notebooks (owner_id, title, description, created_at, is_shared) VALUES (?, ?, ?, ?, ?)',
        (user['id'], title, '', now, is_shared)
    )
    db.commit()
    return redirect(url_for('dashboard'))

# ---------- Notes Routes ----------
@app.route('/note/<int:note_id>')
@login_required
def view_note(note_id):
    db = get_db()
    note = db.execute('SELECT n.*, u.username as author FROM notes n LEFT JOIN users u ON u.id=n.created_by WHERE n.id=?', (note_id,)).fetchone()
    if not note:
        abort(404)
    return render_template('note.html', note=note)

@app.route('/note/create', methods=['POST'])
@login_required
def create_note():
    title = request.form.get('title') or 'Untitled'
    notebook_id = request.form.get('notebook_id')
    content = request.form.get('content') or ''
    user = current_user()
    db = get_db()
    now = datetime.datetime.utcnow().isoformat()
    cur = db.execute(
        'INSERT INTO notes (notebook_id, title, content, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)',
        (notebook_id, title, content, user['id'], now, now)
    )
    db.commit()
    return str(cur.lastrowid)

# ---------- API for Notes ----------
@app.route('/api/note/<int:note_id>', methods=['GET','POST'])
@login_required
def api_note(note_id):
    db = get_db()
    user = current_user()
    if request.method == 'GET':
        note = db.execute('SELECT * FROM notes WHERE id=?', (note_id,)).fetchone()
        if not note: abort(404)
        return jsonify(dict(note))
    else:
        content = request.json.get('content')
        title = request.json.get('title')
        now = datetime.datetime.utcnow().isoformat()
        db.execute('UPDATE notes SET content=?, title=?, updated_at=? WHERE id=?', (content, title, now, note_id))
        db.execute('INSERT INTO contributions (note_id, user_id, action, timestamp, detail) VALUES (?, ?, ?, ?, ?)',
                   (note_id, user['id'], 'edit', now, 'updated via api'))
        db.commit()
        socketio.emit('note_updated', {'note_id': note_id, 'content': content, 'title': title, 'updated_at': now}, room=f'note_{note_id}')
        return jsonify({'status': 'ok'})
@app.route('/get_notes_text/<int:notebook_id>')
@login_required
def get_notes_text(notebook_id):
    db = get_db()
    notes = db.execute('SELECT content FROM notes WHERE notebook_id=? ORDER BY created_at', (notebook_id,)).fetchall()
    if not notes:
        return jsonify({'notes_text': ''})  # no notes
    combined_text = '\n'.join(note['content'] for note in notes if note['content'])
    return jsonify({'notes_text': combined_text})

@app.route('/api/transcript', methods=['POST'])
@login_required
def upload_transcript():
    data = request.json
    note_id = data.get('note_id')
    speaker = data.get('speaker')
    transcript = data.get('transcript')
    if not note_id or not transcript:
        return jsonify({'error': 'note_id and transcript required'}), 400
    db = get_db()
    now = datetime.datetime.utcnow().isoformat()
    note = db.execute('SELECT content FROM notes WHERE id=?', (note_id,)).fetchone()
    if not note:
        return jsonify({'error': 'note not found'}), 404
    new_content = (note['content'] or '') + f"\n[{speaker or 'unknown'} @ {now}]: {transcript}"
    db.execute('UPDATE notes SET content=?, updated_at=? WHERE id=?', (new_content, now, note_id))
    db.execute('INSERT INTO contributions (note_id, user_id, action, timestamp, detail) VALUES (?, ?, ?, ?, ?)',
               (note_id, session.get('user_id'), 'transcript', now, f'speaker={speaker}'))
    db.commit()
    socketio.emit('note_updated', {'note_id': note_id, 'content': new_content, 'updated_at': now}, room=f'note_{note_id}')
    return jsonify({'status': 'ok', 'new_content': new_content})
# ---------- Groups Routes ----------

# Create a new group
@app.route('/group/create', methods=['POST'])
@login_required
def create_group():
    name = request.form.get('name') or 'New Group'
    description = request.form.get('description', '')
    member_names = request.form.getlist('member_name[]')
    member_ids = request.form.getlist('member_id[]')
    member_courses = request.form.getlist('member_course[]')

    now = datetime.datetime.utcnow().isoformat()
    db = get_db()
    cur = db.execute(
        'INSERT INTO groups (name, description, created_at) VALUES (?, ?, ?)',
        (name, description, now)
    )
    group_id = cur.lastrowid

    # Add owner
    db.execute(
        'INSERT INTO group_members (group_id, user_id, role, joined_at) VALUES (?, ?, ?, ?)',
        (group_id, session.get('user_id'), 'owner', now)
    )

    # Add other members
    for uname, sid, course in zip(member_names, member_ids, member_courses):
        user = db.execute('SELECT id FROM users WHERE username=?', (uname,)).fetchone()
        if not user:
            cur2 = db.execute(
                'INSERT INTO users (username, full_name, created_at, password_hash) VALUES (?, ?, ?, ?)',
                (uname, uname, now, generate_password_hash('defaultpass'))
            )
            user_id = cur2.lastrowid
        else:
            user_id = user['id']

        db.execute(
            'INSERT INTO group_members (group_id, user_id, role, joined_at) VALUES (?, ?, ?, ?)',
            (group_id, user_id, 'member', now)
        )
    db.commit()
    return redirect(url_for('dashboard'))


# View a group
@app.route('/group/<int:group_id>')
@login_required
def view_group(group_id):
    db = get_db()
    user = current_user()
    group = db.execute('SELECT * FROM groups WHERE id=?', (group_id,)).fetchone()
    if not group:
        abort(404)

    members = db.execute(
        'SELECT u.id as user_id, u.username, u.full_name, gm.role '
        'FROM group_members gm '
        'JOIN users u ON u.id = gm.user_id '
        'WHERE gm.group_id=?', 
        (group_id,)
    ).fetchall()

    return render_template('group_view.html', user=user, group=group, members=members)


# Show edit form for a group
@app.route('/group/<int:group_id>/edit', methods=['GET'])
@login_required
def edit_group(group_id):
    db = get_db()
    group = db.execute('SELECT * FROM groups WHERE id=?', (group_id,)).fetchone()
    if not group:
        abort(404)

    members = db.execute(
        'SELECT gm.id as gm_id, u.username, u.full_name, u.id as user_id, gm.role '
        'FROM group_members gm JOIN users u ON gm.user_id=u.id WHERE gm.group_id=?',
        (group_id,)
    ).fetchall()
    
    user = current_user()
    return render_template('group_edit.html', group=group, members=members, user=user)


# Update group info and members
@app.route('/group/<int:group_id>/update', methods=['POST'])
@login_required
def update_group(group_id):
    db = get_db()
    group = db.execute('SELECT * FROM groups WHERE id=?', (group_id,)).fetchone()
    if not group:
        abort(404)

    # Update group name/description
    name = request.form.get('name', group['name'])
    description = request.form.get('description', group['description'])
    db.execute('UPDATE groups SET name=?, description=? WHERE id=?', (name, description, group_id))

    # Update members
    member_names = request.form.getlist('member_name[]')
    member_ids = request.form.getlist('member_id[]')
    member_courses = request.form.getlist('member_course[]')

    # Remove previous non-owner members
    db.execute('DELETE FROM group_members WHERE group_id=? AND role!="owner"', (group_id,))
    now = datetime.datetime.utcnow().isoformat()

    for uname, sid, course in zip(member_names, member_ids, member_courses):
        user = db.execute('SELECT id FROM users WHERE username=?', (uname,)).fetchone()
        if not user:
            cur2 = db.execute(
                'INSERT INTO users (username, full_name, created_at, password_hash) VALUES (?, ?, ?, ?)',
                (uname, uname, now, generate_password_hash('defaultpass'))
            )
            user_id = cur2.lastrowid
        else:
            user_id = user['id']

        db.execute(
            'INSERT INTO group_members (group_id, user_id, role, joined_at) VALUES (?, ?, ?, ?)',
            (group_id, user_id, 'member', now)
        )

    db.commit()
    return redirect(url_for('view_group', group_id=group_id))


# Add a member to a group
@app.route('/group/<int:group_id>/add_member', methods=['POST'])
@login_required
def add_member(group_id):
    username = request.form.get('username')
    role = request.form.get('role') or 'member'
    if not username:
        return redirect(url_for('edit_group', group_id=group_id))

    db = get_db()
    now = datetime.datetime.utcnow().isoformat()
    user = db.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()
    if not user:
        cur = db.execute(
            'INSERT INTO users (username, full_name, created_at, password_hash) VALUES (?, ?, ?, ?)',
            (username, username, now, generate_password_hash('defaultpass'))
        )
        user_id = cur.lastrowid
    else:
        user_id = user['id']

    try:
        db.execute(
            'INSERT INTO group_members (group_id, user_id, role, joined_at) VALUES (?, ?, ?, ?)',
            (group_id, user_id, role, now)
        )
        db.commit()
    except sqlite3.IntegrityError:
        pass  # already in group

    return redirect(url_for('edit_group', group_id=group_id))


# Remove a member
@app.route('/group/<int:group_id>/remove_member/<int:user_id>', methods=['POST'])
@login_required
def remove_member(group_id, user_id):
    db = get_db()
    member = db.execute('SELECT role FROM group_members WHERE group_id=? AND user_id=?', (group_id, user_id)).fetchone()
    if member and member['role'] != 'owner':
        db.execute('DELETE FROM group_members WHERE group_id=? AND user_id=?', (group_id, user_id))
        db.commit()
    return redirect(url_for('edit_group', group_id=group_id))


# Delete a group
@app.route('/group/<int:group_id>/delete', methods=['POST'])
@login_required
def delete_group(group_id):
    db = get_db()
    db.execute('DELETE FROM groups WHERE id=?', (group_id,))
    db.commit()
    return redirect(url_for('dashboard'))

# ---------- SocketIO Events ----------
@socketio.on('join_note')
def on_join_note(data):
    note_id = data.get('note_id')
    if not note_id:
        return
    join_room(f'note_{note_id}')
    emit('joined', {'note_id': note_id}, room=request.sid)

@socketio.on('leave_note')
def on_leave_note(data):
    note_id = data.get('note_id')
    if not note_id:
        return
    leave_room(f'note_{note_id}')

@socketio.on('edit')
def on_edit(data):
    note_id = data.get('note_id')
    content = data.get('content')
    title = data.get('title')
    if not note_id or content is None:
        return
    now = datetime.datetime.utcnow().isoformat()
    db = get_db()
    db.execute('UPDATE notes SET content=?, title=?, updated_at=? WHERE id=?', (content, title, now, note_id))
    db.execute('INSERT INTO contributions (note_id, user_id, action, timestamp, detail) VALUES (?, ?, ?, ?, ?)',
               (note_id, session.get('user_id'), 'edit_ws', now, 'live edit'))
    db.commit()
    emit('note_updated', {'note_id': note_id, 'content': content, 'title': title, 'updated_at': now}, room=f'note_{note_id}', include_self=False)

# ---------- Run ----------
if __name__ == '__main__':
    app.secret_key = app.config['SECRET_KEY']
    print('Starting NoteBridge on http://127.0.0.1:5000')
    socketio.run(app, host='0.0.0.0', port=5000, debug=DEBUG)
=======
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
>>>>>>> 43d8451 (Updated code for Sprint 1)
=======
from flask import Flask, g, render_template, request, redirect, url_for, session, jsonify, abort
from werkzeug.security import generate_password_hash, check_password_hash
from flask_socketio import SocketIO, join_room, leave_room, emit
import sqlite3
import os
import datetime

# ---------- Configuration ----------
DATABASE = os.path.join(os.path.dirname(__file__), 'notebridge.db')
SECRET_KEY = os.environ.get('SECRET_KEY', 'qwerty1234')
DEBUG = True

# ---------- Flask App Setup ----------
app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config.update(SECRET_KEY=SECRET_KEY, DEBUG=DEBUG)
socketio = SocketIO(app, cors_allowed_origins="*")

# ---------- Database Utilities ----------
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    schema = """
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS group_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        role TEXT DEFAULT 'member',
        joined_at TEXT NOT NULL,
        FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS notebooks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        created_at TEXT NOT NULL,
        is_shared INTEGER DEFAULT 0,
        FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        notebook_id INTEGER NOT NULL,
        title TEXT,
        content TEXT,
        created_by INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT,
        FOREIGN KEY(notebook_id) REFERENCES notebooks(id) ON DELETE CASCADE,
        FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS contributions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        note_id INTEGER NOT NULL,
        user_id INTEGER,
        action TEXT,
        timestamp TEXT NOT NULL,
        detail TEXT,
        FOREIGN KEY(note_id) REFERENCES notes(id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        note_id INTEGER NOT NULL,
        tag TEXT NOT NULL,
        FOREIGN KEY(note_id) REFERENCES notes(id) ON DELETE CASCADE
    );
    """
    db = get_db()
    db.executescript(schema)
    db.commit()

if not os.path.exists(DATABASE):
    with app.app_context():
        init_db()
        print('Initialized database at', DATABASE)

# ---------- Authentication Helpers ----------
def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    db = get_db()
    user = db.execute('SELECT id, username, full_name, created_at FROM users WHERE id=?', (uid,)).fetchone()
    return user

def login_required(f):
    from functools import wraps
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return wrapped

# ---------- Auth Routes ----------
@app.route('/')
def index():
    user = current_user()
    if user:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        full_name = request.form.get('full_name')
        if not username or not password:
            return 'Missing username or password', 400
        db = get_db()
        try:
            db.execute('INSERT INTO users (username, password_hash, full_name, created_at) VALUES (?, ?, ?, ?)',
                       (username, generate_password_hash(password), full_name, datetime.datetime.utcnow().isoformat()))
            db.commit()
        except sqlite3.IntegrityError:
            return 'Username already exists', 400
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            return redirect(url_for('dashboard'))
        return 'Invalid credentials', 400
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ---------- Dashboard ----------
@app.route('/dashboard')
@login_required
def dashboard():
    user = current_user()
    db = get_db()
    notebooks = db.execute('SELECT * FROM notebooks WHERE owner_id=?', (user['id'],)).fetchall()
    shared_notebooks = db.execute(
        'SELECT n.* FROM notebooks n '
        'JOIN group_members gm ON gm.user_id=? '
        'JOIN groups g ON g.id=gm.group_id '
        'WHERE n.is_shared=1', 
        (user['id'],)
    ).fetchall()
    groups = db.execute(
        'SELECT g.*, (SELECT COUNT(*) FROM group_members gm WHERE gm.group_id=g.id) AS members FROM groups g'
    ).fetchall()
    return render_template('dashboard.html', user=user, notebooks=notebooks, shared_notebooks=shared_notebooks, groups=groups)

# ---------- Notebook Routes ----------
@app.route('/notebook/<int:notebook_id>')
@login_required
def view_notebook(notebook_id):
    db = get_db()
    nb = db.execute('SELECT * FROM notebooks WHERE id=?', (notebook_id,)).fetchone()
    if not nb:
        abort(404)
    notes = db.execute('SELECT * FROM notes WHERE notebook_id=? ORDER BY updated_at DESC NULLS LAST, created_at DESC', (notebook_id,)).fetchall()
    return render_template('notebook.html', notebook=nb, notes=notes)

@app.route('/notebook/create', methods=['POST'])
@login_required
def create_notebook():
    title = request.form.get('title') or 'Untitled Notebook'
    is_shared = 1 if request.form.get('is_shared') else 0
    user = current_user()
    now = datetime.datetime.utcnow().isoformat()
    db = get_db()
    db.execute(
        'INSERT INTO notebooks (owner_id, title, description, created_at, is_shared) VALUES (?, ?, ?, ?, ?)',
        (user['id'], title, '', now, is_shared)
    )
    db.commit()
    return redirect(url_for('dashboard'))

# ---------- Notes Routes ----------
@app.route('/note/<int:note_id>')
@login_required
def view_note(note_id):
    db = get_db()
    note = db.execute('SELECT n.*, u.username as author FROM notes n LEFT JOIN users u ON u.id=n.created_by WHERE n.id=?', (note_id,)).fetchone()
    if not note:
        abort(404)
    return render_template('note.html', note=note)

@app.route('/note/create', methods=['POST'])
@login_required
def create_note():
    title = request.form.get('title') or 'Untitled'
    notebook_id = request.form.get('notebook_id')
    content = request.form.get('content') or ''
    user = current_user()
    db = get_db()
    now = datetime.datetime.utcnow().isoformat()
    cur = db.execute(
        'INSERT INTO notes (notebook_id, title, content, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)',
        (notebook_id, title, content, user['id'], now, now)
    )
    db.commit()
    return str(cur.lastrowid)

# ---------- API for Notes ----------
@app.route('/api/note/<int:note_id>', methods=['GET','POST'])
@login_required
def api_note(note_id):
    db = get_db()
    user = current_user()
    if request.method == 'GET':
        note = db.execute('SELECT * FROM notes WHERE id=?', (note_id,)).fetchone()
        if not note: abort(404)
        return jsonify(dict(note))
    else:
        content = request.json.get('content')
        title = request.json.get('title')
        now = datetime.datetime.utcnow().isoformat()
        db.execute('UPDATE notes SET content=?, title=?, updated_at=? WHERE id=?', (content, title, now, note_id))
        db.execute('INSERT INTO contributions (note_id, user_id, action, timestamp, detail) VALUES (?, ?, ?, ?, ?)',
                   (note_id, user['id'], 'edit', now, 'updated via api'))
        db.commit()
        socketio.emit('note_updated', {'note_id': note_id, 'content': content, 'title': title, 'updated_at': now}, room=f'note_{note_id}')
        return jsonify({'status': 'ok'})
@app.route('/get_notes_text/<int:notebook_id>')
@login_required
def get_notes_text(notebook_id):
    db = get_db()
    notes = db.execute('SELECT content FROM notes WHERE notebook_id=? ORDER BY created_at', (notebook_id,)).fetchall()
    if not notes:
        return jsonify({'notes_text': ''})  # no notes
    combined_text = '\n'.join(note['content'] for note in notes if note['content'])
    return jsonify({'notes_text': combined_text})

@app.route('/api/transcript', methods=['POST'])
@login_required
def upload_transcript():
    data = request.json
    note_id = data.get('note_id')
    speaker = data.get('speaker')
    transcript = data.get('transcript')
    if not note_id or not transcript:
        return jsonify({'error': 'note_id and transcript required'}), 400
    db = get_db()
    now = datetime.datetime.utcnow().isoformat()
    note = db.execute('SELECT content FROM notes WHERE id=?', (note_id,)).fetchone()
    if not note:
        return jsonify({'error': 'note not found'}), 404
    new_content = (note['content'] or '') + f"\n[{speaker or 'unknown'} @ {now}]: {transcript}"
    db.execute('UPDATE notes SET content=?, updated_at=? WHERE id=?', (new_content, now, note_id))
    db.execute('INSERT INTO contributions (note_id, user_id, action, timestamp, detail) VALUES (?, ?, ?, ?, ?)',
               (note_id, session.get('user_id'), 'transcript', now, f'speaker={speaker}'))
    db.commit()
    socketio.emit('note_updated', {'note_id': note_id, 'content': new_content, 'updated_at': now}, room=f'note_{note_id}')
    return jsonify({'status': 'ok', 'new_content': new_content})
# ---------- Groups Routes ----------

# Create a new group
@app.route('/group/create', methods=['POST'])
@login_required
def create_group():
    name = request.form.get('name') or 'New Group'
    description = request.form.get('description', '')
    member_names = request.form.getlist('member_name[]')
    member_ids = request.form.getlist('member_id[]')
    member_courses = request.form.getlist('member_course[]')

    now = datetime.datetime.utcnow().isoformat()
    db = get_db()
    cur = db.execute(
        'INSERT INTO groups (name, description, created_at) VALUES (?, ?, ?)',
        (name, description, now)
    )
    group_id = cur.lastrowid

    # Add owner
    db.execute(
        'INSERT INTO group_members (group_id, user_id, role, joined_at) VALUES (?, ?, ?, ?)',
        (group_id, session.get('user_id'), 'owner', now)
    )

    # Add other members
    for uname, sid, course in zip(member_names, member_ids, member_courses):
        user = db.execute('SELECT id FROM users WHERE username=?', (uname,)).fetchone()
        if not user:
            cur2 = db.execute(
                'INSERT INTO users (username, full_name, created_at, password_hash) VALUES (?, ?, ?, ?)',
                (uname, uname, now, generate_password_hash('defaultpass'))
            )
            user_id = cur2.lastrowid
        else:
            user_id = user['id']

        db.execute(
            'INSERT INTO group_members (group_id, user_id, role, joined_at) VALUES (?, ?, ?, ?)',
            (group_id, user_id, 'member', now)
        )
    db.commit()
    return redirect(url_for('dashboard'))


# View a group
@app.route('/group/<int:group_id>')
@login_required
def view_group(group_id):
    db = get_db()
    user = current_user()
    group = db.execute('SELECT * FROM groups WHERE id=?', (group_id,)).fetchone()
    if not group:
        abort(404)

    members = db.execute(
        'SELECT u.id as user_id, u.username, u.full_name, gm.role '
        'FROM group_members gm '
        'JOIN users u ON u.id = gm.user_id '
        'WHERE gm.group_id=?', 
        (group_id,)
    ).fetchall()

    return render_template('group_view.html', user=user, group=group, members=members)


# Show edit form for a group
@app.route('/group/<int:group_id>/edit', methods=['GET'])
@login_required
def edit_group(group_id):
    db = get_db()
    group = db.execute('SELECT * FROM groups WHERE id=?', (group_id,)).fetchone()
    if not group:
        abort(404)

    members = db.execute(
        'SELECT gm.id as gm_id, u.username, u.full_name, u.id as user_id, gm.role '
        'FROM group_members gm JOIN users u ON gm.user_id=u.id WHERE gm.group_id=?',
        (group_id,)
    ).fetchall()
    
    user = current_user()
    return render_template('group_edit.html', group=group, members=members, user=user)


# Update group info and members
@app.route('/group/<int:group_id>/update', methods=['POST'])
@login_required
def update_group(group_id):
    db = get_db()
    group = db.execute('SELECT * FROM groups WHERE id=?', (group_id,)).fetchone()
    if not group:
        abort(404)

    # Update group name/description
    name = request.form.get('name', group['name'])
    description = request.form.get('description', group['description'])
    db.execute('UPDATE groups SET name=?, description=? WHERE id=?', (name, description, group_id))

    # Update members
    member_names = request.form.getlist('member_name[]')
    member_ids = request.form.getlist('member_id[]')
    member_courses = request.form.getlist('member_course[]')

    # Remove previous non-owner members
    db.execute('DELETE FROM group_members WHERE group_id=? AND role!="owner"', (group_id,))
    now = datetime.datetime.utcnow().isoformat()

    for uname, sid, course in zip(member_names, member_ids, member_courses):
        user = db.execute('SELECT id FROM users WHERE username=?', (uname,)).fetchone()
        if not user:
            cur2 = db.execute(
                'INSERT INTO users (username, full_name, created_at, password_hash) VALUES (?, ?, ?, ?)',
                (uname, uname, now, generate_password_hash('defaultpass'))
            )
            user_id = cur2.lastrowid
        else:
            user_id = user['id']

        db.execute(
            'INSERT INTO group_members (group_id, user_id, role, joined_at) VALUES (?, ?, ?, ?)',
            (group_id, user_id, 'member', now)
        )

    db.commit()
    return redirect(url_for('view_group', group_id=group_id))


# Add a member to a group
@app.route('/group/<int:group_id>/add_member', methods=['POST'])
@login_required
def add_member(group_id):
    username = request.form.get('username')
    role = request.form.get('role') or 'member'
    if not username:
        return redirect(url_for('edit_group', group_id=group_id))

    db = get_db()
    now = datetime.datetime.utcnow().isoformat()
    user = db.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()
    if not user:
        cur = db.execute(
            'INSERT INTO users (username, full_name, created_at, password_hash) VALUES (?, ?, ?, ?)',
            (username, username, now, generate_password_hash('defaultpass'))
        )
        user_id = cur.lastrowid
    else:
        user_id = user['id']

    try:
        db.execute(
            'INSERT INTO group_members (group_id, user_id, role, joined_at) VALUES (?, ?, ?, ?)',
            (group_id, user_id, role, now)
        )
        db.commit()
    except sqlite3.IntegrityError:
        pass  # already in group

    return redirect(url_for('edit_group', group_id=group_id))


# Remove a member
@app.route('/group/<int:group_id>/remove_member/<int:user_id>', methods=['POST'])
@login_required
def remove_member(group_id, user_id):
    db = get_db()
    member = db.execute('SELECT role FROM group_members WHERE group_id=? AND user_id=?', (group_id, user_id)).fetchone()
    if member and member['role'] != 'owner':
        db.execute('DELETE FROM group_members WHERE group_id=? AND user_id=?', (group_id, user_id))
        db.commit()
    return redirect(url_for('edit_group', group_id=group_id))


# Delete a group
@app.route('/group/<int:group_id>/delete', methods=['POST'])
@login_required
def delete_group(group_id):
    db = get_db()
    db.execute('DELETE FROM groups WHERE id=?', (group_id,))
    db.commit()
    return redirect(url_for('dashboard'))

# ---------- SocketIO Events ----------
@socketio.on('join_note')
def on_join_note(data):
    note_id = data.get('note_id')
    if not note_id:
        return
    join_room(f'note_{note_id}')
    emit('joined', {'note_id': note_id}, room=request.sid)

@socketio.on('leave_note')
def on_leave_note(data):
    note_id = data.get('note_id')
    if not note_id:
        return
    leave_room(f'note_{note_id}')

@socketio.on('edit')
def on_edit(data):
    note_id = data.get('note_id')
    content = data.get('content')
    title = data.get('title')
    if not note_id or content is None:
        return
    now = datetime.datetime.utcnow().isoformat()
    db = get_db()
    db.execute('UPDATE notes SET content=?, title=?, updated_at=? WHERE id=?', (content, title, now, note_id))
    db.execute('INSERT INTO contributions (note_id, user_id, action, timestamp, detail) VALUES (?, ?, ?, ?, ?)',
               (note_id, session.get('user_id'), 'edit_ws', now, 'live edit'))
    db.commit()
    emit('note_updated', {'note_id': note_id, 'content': content, 'title': title, 'updated_at': now}, room=f'note_{note_id}', include_self=False)

# ---------- Run ----------
if __name__ == '__main__':
    app.secret_key = app.config['SECRET_KEY']
    print('Starting NoteBridge on http://127.0.0.1:5000')
    socketio.run(app, host='0.0.0.0', port=5000, debug=DEBUG)
>>>>>>> origin/main
