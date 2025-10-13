from flask import Blueprint, render_template, request, jsonify
from auth import login_required, current_user
from database import get_db
import datetime

# Blueprint for notebook and note routes
notebook_bp = Blueprint('notebook', __name__, url_prefix='')

# NOTEBOOK CRUD

# View a notebook and its notes
@notebook_bp.route('/notebook/<int:notebook_id>')
@login_required
def view_notebook(notebook_id):
    db = get_db()
    nb = db.execute('SELECT * FROM notebooks WHERE id=?', (notebook_id,)).fetchone()
    if not nb:
        return "Notebook not found", 404

    notes = db.execute(
        'SELECT * FROM notes WHERE notebook_id=? ORDER BY updated_at DESC, created_at DESC',
        (notebook_id,)
    ).fetchall()

    return render_template('notebook.html', notebook=nb, notes=notes)


# Create a new notebook
@notebook_bp.route('/notebook/create', methods=['POST'])
@login_required
def create_notebook():
    title = request.form.get('title') or 'Untitled Notebook'
    is_shared = 1 if request.form.get('is_shared') else 0
    user = current_user()
    now = datetime.datetime.utcnow().isoformat()
    db = get_db()

    cur = db.execute(
        'INSERT INTO notebooks (owner_id, title, description, created_at, is_shared) VALUES (?, ?, ?, ?, ?)',
        (user['id'], title, '', now, is_shared)
    )
    db.commit()
    return jsonify({'notebook_id': cur.lastrowid, 'message': 'Notebook created'}), 200


# Update a notebook
@notebook_bp.route('/notebook/<int:notebook_id>', methods=['PUT'])
@login_required
def update_notebook(notebook_id):
    db = get_db()
    notebook = db.execute('SELECT * FROM notebooks WHERE id=?', (notebook_id,)).fetchone()
    if not notebook:
        return jsonify({'error': 'Notebook not found'}), 404

    user = current_user()
    if notebook['owner_id'] != user['id']:
        return jsonify({'error': 'Unauthorized'}), 403

    # Support JSON or URL-encoded form data
    data = request.get_json() or request.form
    title = data.get('title', notebook['title'])
    description = data.get('description', notebook.get('description', ''))
    is_shared = int(data.get('is_shared', notebook['is_shared']))

    db.execute(
        'UPDATE notebooks SET title=?, description=?, is_shared=? WHERE id=?',
        (title, description, is_shared, notebook_id)
    )
    db.commit()
    return jsonify({'message': 'Notebook updated'})


# Delete a notebook
@notebook_bp.route('/notebook/<int:notebook_id>', methods=['DELETE'])
@login_required
def delete_notebook(notebook_id):
    db = get_db()
    notebook = db.execute('SELECT * FROM notebooks WHERE id=?', (notebook_id,)).fetchone()
    if not notebook:
        return jsonify({'error': 'Notebook not found'}), 404

    user = current_user()
    if notebook['owner_id'] != user['id']:
        return jsonify({'error': 'Unauthorized'}), 403

    # Delete all notes inside the notebook first
    db.execute('DELETE FROM notes WHERE notebook_id=?', (notebook_id,))
    db.execute('DELETE FROM notebooks WHERE id=?', (notebook_id,))
    db.commit()
    return jsonify({'message': 'Notebook and all notes deleted'})

# NOTE CRUD

# View a single note
@notebook_bp.route('/note/<int:note_id>')
@login_required
def view_note(note_id):
    db = get_db()
    note = db.execute(
        'SELECT n.*, u.username as author FROM notes n LEFT JOIN users u ON u.id=n.created_by WHERE n.id=?',
        (note_id,)
    ).fetchone()

    if not note:
        return "Note not found", 404

    notebook = db.execute('SELECT * FROM notebooks WHERE id=?', (note['notebook_id'],)).fetchone()
    return render_template('note.html', note=note, notebook=notebook)


# Create a new note
@notebook_bp.route('/note/create', methods=['POST'])
@login_required
def create_note():
    title = request.form.get('title') or 'Untitled'
    notebook_id = request.form.get('notebook_id')
    if not notebook_id or not notebook_id.isdigit():
        return jsonify({'error': 'Invalid notebook ID'}), 400

    notebook_id = int(notebook_id)
    content = request.form.get('content') or ''
    user = current_user()
    now = datetime.datetime.utcnow().isoformat()
    db = get_db()

    cur = db.execute(
        'INSERT INTO notes (notebook_id, title, content, created_by, created_at, updated_at) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (notebook_id, title, content, user['id'], now, now)
    )
    db.commit()
    return jsonify({'note_id': cur.lastrowid, 'message': 'Note created'})


# Update a note
@notebook_bp.route('/note/<int:note_id>', methods=['PUT'])
@login_required
def update_note(note_id):
    db = get_db()
    note = db.execute('SELECT * FROM notes WHERE id=?', (note_id,)).fetchone()
    if not note:
        return jsonify({'error': 'Note not found'}), 404

    user = current_user()
    if note['created_by'] != user['id']:
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json() or request.form
    title = data.get('title', note['title'])
    content = data.get('content', note['content'])
    now = datetime.datetime.utcnow().isoformat()

    db.execute(
        'UPDATE notes SET title=?, content=?, updated_at=? WHERE id=?',
        (title, content, now, note_id)
    )
    db.commit()
    return jsonify({'message': 'Note updated'})


# Delete a note
@notebook_bp.route('/note/<int:note_id>', methods=['DELETE'])
@login_required
def delete_note(note_id):
    db = get_db()
    note = db.execute('SELECT * FROM notes WHERE id=?', (note_id,)).fetchone()
    if not note:
        return jsonify({'error': 'Note not found'}), 404

    user = current_user()
    if note['created_by'] != user['id']:
        return jsonify({'error': 'Unauthorized'}), 403

    db.execute('DELETE FROM notes WHERE id=?', (note_id,))
    db.commit()
    return jsonify({'message': 'Note deleted'})
