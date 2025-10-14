from flask import Blueprint, redirect, render_template, request, jsonify, url_for
from auth import login_required, current_user
from database import get_db
import datetime
import re

notebook_bp = Blueprint('notebook', __name__, url_prefix='')

@notebook_bp.route('/notebooks', methods=['GET'])
@login_required
def list_notebooks():
    user = current_user()
    db = get_db()
    # Fetch all notebooks owned by the user
    notebooks = db.execute(
        'SELECT id, title FROM notebooks WHERE owner_id=? ORDER BY created_at DESC',
        (user['id'],)
    ).fetchall()
    # Fetch groups for sidebar
    groups = db.execute(
        'SELECT g.id, g.name, (SELECT COUNT(*) FROM group_members gm WHERE gm.group_id=g.id) AS members FROM groups g'
    ).fetchall()
    return render_template('dashboard.html', user=user, notebooks=notebooks, groups=groups)

@notebook_bp.route('/notebook/<int:notebook_id>')
@login_required
def view_notebook(notebook_id):
    db = get_db()
    # Get notebook by ID
    nb = db.execute('SELECT * FROM notebooks WHERE id=?', (notebook_id,)).fetchone()
    if not nb:
        return "Notebook not found", 404
    # Get notes in notebook
    notes = db.execute(
        'SELECT * FROM notes WHERE notebook_id=? ORDER BY updated_at DESC, created_at DESC',
        (notebook_id,)
    ).fetchall()
    return render_template('notebook.html', notebook=nb, notes=notes)

@notebook_bp.route('/notebook/create', methods=['GET', 'POST'])
@login_required
def create_notebook():
    user = current_user()
    db = get_db()
    if request.method == 'POST':
        # Create new notebook
        title = request.form.get('title') or 'Untitled Notebook'
        is_shared = 1 if request.form.get('is_shared') else 0
        now = datetime.datetime.utcnow().isoformat()
        cur = db.execute(
            'INSERT INTO notebooks (owner_id, title, description, created_at, is_shared) VALUES (?, ?, ?, ?, ?)',
            (user['id'], title, '', now, is_shared)
        )
        db.commit()
        return redirect(url_for('notebook.view_notebook', notebook_id=cur.lastrowid))
    # Show dashboard if GET
    notebooks = db.execute('SELECT id, title FROM notebooks WHERE owner_id=?', (user['id'],)).fetchall()
    groups = db.execute(
        'SELECT g.id, g.name, (SELECT COUNT(*) FROM group_members gm WHERE gm.group_id=g.id) AS members FROM groups g'
    ).fetchall()
    return render_template('dashboard.html', user=user, notebooks=notebooks, groups=groups)

@notebook_bp.route('/notebook/<int:notebook_id>', methods=['PUT'])
@login_required
def update_notebook(notebook_id):
    db = get_db()
    notebook = db.execute('SELECT * FROM notebooks WHERE id=?', (notebook_id,)).fetchone()
    if not notebook:
        return jsonify({'error': 'notebook not found'}), 404
    user = current_user()
    if notebook['owner_id'] != user['id']:
        return jsonify({'error': 'unauthorized'}), 403
    data = request.get_json() or request.form
    title = data.get('title', notebook['title'])
    description = data.get('description', notebook.get('description', ''))
    is_shared = int(data.get('is_shared', notebook['is_shared']))
    db.execute(
        'UPDATE notebooks SET title=?, description=?, is_shared=? WHERE id=?',
        (title, description, is_shared, notebook_id)
    )
    db.commit()
    return jsonify({'message': 'notebook updated'})

@notebook_bp.route('/notebook/delete/<int:notebook_id>', methods=['POST'])
@login_required
def delete_notebook(notebook_id):
    db = get_db()
    notebook = db.execute('SELECT * FROM notebooks WHERE id=?', (notebook_id,)).fetchone()
    if not notebook:
        return "Notebook not found", 404
    user = current_user()
    if notebook['owner_id'] != user['id']:
        return "Unauthorized", 403
    db.execute('DELETE FROM notes WHERE notebook_id=?', (notebook_id,))
    db.execute('DELETE FROM notebooks WHERE id=?', (notebook_id,))
    db.commit()
    return redirect(url_for('notebook.list_notebooks'))

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

@notebook_bp.route('/note/create', methods=['POST'])
@login_required
def create_note():
    title = request.form.get('title') or 'Untitled'
    notebook_id = request.form.get('notebook_id')
    if not notebook_id or not notebook_id.isdigit():
        return jsonify({'error': 'invalid notebook id'}), 400
    notebook_id = int(notebook_id)
    content = request.form.get('content') or ''
    user = current_user()
    now = datetime.datetime.utcnow().isoformat()
    db = get_db()
    cur = db.execute(
        'INSERT INTO notes (notebook_id, title, content, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)',
        (notebook_id, title, content, user['id'], now, now)
    )
    db.commit()
    return jsonify({'note_id': cur.lastrowid, 'message': 'note created'})

@notebook_bp.route('/note/<int:note_id>', methods=['PUT'])
@login_required
def update_note(note_id):
    db = get_db()
    note = db.execute('SELECT * FROM notes WHERE id=?', (note_id,)).fetchone()
    if not note:
        return jsonify({'error': 'note not found'}), 404
    user = current_user()
    if note['created_by'] != user['id']:
        return jsonify({'error': 'unauthorized'}), 403
    data = request.get_json() or request.form
    title = data.get('title', note['title'])
    content = data.get('content', note['content'])
    now = datetime.datetime.utcnow().isoformat()
    db.execute(
        'UPDATE notes SET title=?, content=?, updated_at=? WHERE id=?',
        (title, content, now, note_id)
    )
    db.commit()
    return jsonify({'message': 'note updated'})

@notebook_bp.route('/note/<int:note_id>', methods=['DELETE'])
@login_required
def delete_note(note_id):
    db = get_db()
    note = db.execute('SELECT * FROM notes WHERE id=?', (note_id,)).fetchone()
    if not note:
        return jsonify({'error': 'note not found'}), 404
    user = current_user()
    if note['created_by'] != user['id']:
        return jsonify({'error': 'unauthorized'}), 403
    db.execute('DELETE FROM notes WHERE id=?', (note_id,))
    db.commit()
    return jsonify({'message': 'note deleted'})

@notebook_bp.route('/notebook/<int:notebook_id>/summarize', methods=['GET'])
@login_required
def summarize_notebook(notebook_id):
    db = get_db()
    notebook = db.execute('SELECT * FROM notebooks WHERE id=?', (notebook_id,)).fetchone()
    if not notebook:
        return jsonify({'error': 'notebook not found'}), 404
    notes = db.execute(
        'SELECT title, content FROM notes WHERE notebook_id=? ORDER BY updated_at DESC',
        (notebook_id,)
    ).fetchall()
    if not notes:
        return jsonify({'summary': "this notebook has no notes to summarize."})
    full_text = " ".join(f"{n['title']}. {n['content']}" for n in notes if n['content']).strip()
    if not full_text:
        return jsonify({'summary': "notebook content is empty."})
    sentences = re.split(r'(?<=[.!?]) +', full_text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) <= 3:
        return jsonify({'summary': full_text})
    words = re.findall(r'\w+', full_text.lower())
    freq = {}
    for w in words:
        if len(w) > 3:
            freq[w] = freq.get(w, 0) + 1
    scored = [(sum(freq.get(w, 0) for w in s.lower().split()), s) for s in sentences]
    top_sentences = [s for _, s in sorted(scored, reverse=True)[:5]]
    summary = " ".join(top_sentences).strip()
    return jsonify({'notebook_id': notebook_id, 'notebook_title': notebook['title'], 'summary': summary or "no meaningful summary generated."})

@notebook_bp.route('/search_notebooks')
@login_required
def search_notebooks():
    query = (request.args.get('query') or '').strip().lower()
    user = current_user()
    db = get_db()
    results = []
    notebooks = db.execute('SELECT id, title FROM notebooks WHERE owner_id=?', (user['id'],)).fetchall()
    for nb in notebooks:
        notes = db.execute('SELECT id, title, content FROM notes WHERE notebook_id=?', (nb['id'],)).fetchall()
        for note in notes:
            combined_text = f"{note['title']} {note['content']}"
            combined_text_lower = combined_text.lower()
            if query in combined_text_lower:
                index = combined_text_lower.find(query)
                start = max(0, index - 50)
                end = min(len(combined_text), index + len(query) + 50)
                snippet = combined_text[start:end].replace("\n", " ")
                results.append({'notebook_id': nb['id'], 'note_id': note['id'], 'note_title': note['title'], 'snippet': snippet})
    return jsonify(results)
