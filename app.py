from flask import Flask, Blueprint, render_template, request, jsonify, send_file
from flask_socketio import SocketIO, join_room, leave_room, emit
from config import SECRET_KEY, DEBUG, DATABASE
from database import get_db, close_connection, init_db
from auth import auth_bp, login_required, current_user
from dashboard import dashboard_bp
from notebooks import notebook_bp
from groups import group_bp
import os
import pyttsx3
from tempfile import NamedTemporaryFile

# -----------------------------
# Help Blueprint
# -----------------------------
help_bp = Blueprint('help', __name__, url_prefix='/help', template_folder='templates')

@help_bp.route('', methods=['GET'])
@login_required
def help_page():
    """Render the Help page (accessible to logged-in users only)."""
    user = current_user()
    return render_template('help.html', user=user)

# -----------------------------
# Chatbot Blueprint
# -----------------------------
chatbot_bp = Blueprint('chatbot', __name__, template_folder='templates')

@chatbot_bp.route('/chatbot', methods=['GET'])
@login_required
def chatbot_page():
    """Render chatbot page with all notebooks available."""
    user = current_user()
    db = get_db()
    notebooks = db.execute(
        'SELECT id, title FROM notebooks WHERE owner_id=? ORDER BY created_at DESC',
        (user['id'],)
    ).fetchall()
    # Convert to list of dicts (for |tojson)
    notebooks_list = [dict(nb) for nb in notebooks]
    return render_template('chatbot.html', user=user, notebooks=notebooks_list)


# -----------------------------
# Flask App Configuration
# -----------------------------
app = Flask(__name__)
app.config.update(
    SECRET_KEY=SECRET_KEY,
    DEBUG=DEBUG,
    DATABASE=DATABASE
)

socketio = SocketIO(app, cors_allowed_origins="*")

# -----------------------------
# Blueprint Registration
# -----------------------------
app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(notebook_bp)
app.register_blueprint(group_bp)
app.register_blueprint(help_bp)
app.register_blueprint(chatbot_bp)

# -----------------------------
# Database Management
# -----------------------------
app.teardown_appcontext(close_connection)

# Initialize DB if it doesn’t exist
if not os.path.exists(DATABASE):
    with app.app_context():
        db = get_db()
        init_db(db)
        print("Database initialized successfully.")

# -----------------------------
# Socket.IO Events
# -----------------------------
@socketio.on('join_note')
def handle_join(data):
    note_id = data.get('note_id')
    if note_id:
        join_room(f"note_{note_id}")
        print(f"User joined note {note_id}")
        emit('status', {'msg': f'Joined note {note_id}'}, room=f"note_{note_id}")

@socketio.on('edit')
def handle_edit(data):
    note_id = data.get('note_id')
    if note_id:
        emit('update', data, room=f"note_{note_id}", include_self=False)

# -----------------------------
# Text-to-Speech Route
# -----------------------------
@app.route('/note/<int:note_id>/speak', methods=['POST'])
@login_required
def speak_note(note_id):
    db = get_db()
    note = db.execute("SELECT title, content FROM notes WHERE id=?", (note_id,)).fetchone()
    if not note:
        return jsonify({"error": "Note not found"}), 404

    data = request.get_json() or {}
    voice_type = data.get("voice", "male")

    engine = pyttsx3.init()
    voices = engine.getProperty('voices')

    selected_voice = None
    for v in voices:
        if voice_type == "female" and "female" in v.name.lower():
            selected_voice = v.id
            break
        elif voice_type == "male" and "male" in v.name.lower():
            selected_voice = v.id
            break
    if selected_voice:
        engine.setProperty('voice', selected_voice)

    engine.setProperty('rate', 170)

    tmp_file = NamedTemporaryFile(delete=False, suffix=".wav")
    tmp_path = tmp_file.name
    tmp_file.close()

    text = note['content'] or "This note is empty."
    engine.save_to_file(text, tmp_path)
    engine.runAndWait()

    return send_file(tmp_path, mimetype='audio/wav', as_attachment=False)

# -----------------------------
# Run the App
# -----------------------------
if __name__ == '__main__':
    print('Starting NoteBridge on http://127.0.0.1:5000')
    socketio.run(app, host='0.0.0.0', port=5000, debug=DEBUG)
