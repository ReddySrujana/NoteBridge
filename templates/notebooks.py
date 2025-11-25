from flask import Blueprint, redirect, render_template, request, jsonify, url_for, send_file, Response, stream_with_context
from auth import login_required, current_user
from database import get_db
import datetime
from datetime import datetime as dt
import re
import pyttsx3
from tempfile import NamedTemporaryFile
from io import BytesIO
import os
import torch
import json
import time
import numpy as np
from transformers import pipeline
# -----------------------------
# Notebook Blueprint
# -----------------------------

notebook_bp = Blueprint('notebook', __name__, url_prefix='/notebook')

# SSE subscribers: notebook_id -> list of queues
notebook_subscribers = {}

# -----------------------------

# notebook routes

# route to list notebooks
@notebook_bp.route('/notebooks', methods=['GET'])
@login_required
def list_notebooks():
    """📘 List all notebooks for the logged-in user."""
    user = current_user()
    db = get_db()
    notebooks = db.execute(
        'SELECT id, title FROM notebooks WHERE owner_id=? ORDER BY created_at DESC',
        (user['id'],)
    ).fetchall()
    groups = db.execute(
        'SELECT g.id, g.name, (SELECT COUNT(*) FROM group_members gm WHERE gm.group_id=g.id) AS members FROM groups g'
    ).fetchall()
    return render_template('dashboard.html', user=user, notebooks=notebooks, groups=groups, current_user=user)

# route for viewing a specific notebook
@notebook_bp.route('/notebook/<int:notebook_id>')
@login_required
def view_notebook(notebook_id):
    """📘 View a specific notebook and its notes."""
    db = get_db()
    nb = db.execute('SELECT * FROM notebooks WHERE id=?', (notebook_id,)).fetchone()
    if not nb:
        return "Notebook not found", 404
    notes = db.execute(
        'SELECT * FROM notes WHERE notebook_id=? ORDER BY updated_at DESC, created_at DESC',
        (notebook_id,)
    ).fetchall()
    return render_template('notebook.html', notebook=nb, notes=notes, current_user=current_user())


# ✅ Create new notebook route
@notebook_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_notebook():
    """📘 Create a new notebook."""
    user = current_user()
    db = get_db()

    if request.method == 'POST':
        title = request.form.get('title', '').strip() or 'Untitled Notebook'
        description = request.form.get('description', '').strip()
        is_shared = 1 if request.form.get('is_shared') else 0
        now = datetime.datetime.utcnow().isoformat()

        cur = db.execute(
            '''
            INSERT INTO notebooks (owner_id, title, description, created_at, is_shared)
            VALUES (?, ?, ?, ?, ?)
            ''',
            (user['id'], title, description, now, is_shared)
        )
        db.commit()

        new_id = cur.lastrowid
        print(f"✅ Created new notebook (ID: {new_id}) titled '{title}' for user {user['id']}")

        # If AJAX (used by voice or fetch)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'status': 'success',
                'notebook_id': new_id,
                'redirect_url': url_for('notebook.view_notebook', notebook_id=new_id)
            })

        # Regular form submission
        return redirect(url_for('notebook.view_notebook', notebook_id=new_id))

    # --- GET request: render creation form ---
    print(f"🧱 Rendering notebook creation form for user {user['id']}")
    return render_template('notebook_create.html', user=user)
# route for updating notebook metadata
@notebook_bp.route('/notebook/<int:notebook_id>', methods=['PUT'])
@login_required
def update_notebook(notebook_id):
    """📘 Update notebook metadata."""
    db = get_db()
    notebook = db.execute('SELECT * FROM notebooks WHERE id=?', (notebook_id,)).fetchone()
    if not notebook:
        return jsonify({'error': 'notebook not found'}), 404
    user = current_user()
    if notebook['owner_id'] != user['id']:
        return jsonify({'error': 'unauthorized'}), 403

    data = request.get_json() or request.form
    title = data.get('title', notebook['title'])
    description = data.get('description', notebook['description'])
    is_shared = int(data.get('is_shared', notebook['is_shared']))
    db.execute(
        'UPDATE notebooks SET title=?, description=?, is_shared=? WHERE id=?',
        (title, description, is_shared, notebook_id)
    )
    db.commit()
    return jsonify({'message': 'notebook updated'})

# route for deleting a notebook
@notebook_bp.route('/notebook/delete/<int:notebook_id>', methods=['POST'])
@login_required
def delete_notebook(notebook_id):
    """📘 Delete a notebook and its notes."""
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

# Note routes

@notebook_bp.route('/note/<int:note_id>')
@login_required
def view_note(note_id):
    """📝 View a specific note."""
    db = get_db()
    note = db.execute(
        'SELECT n.*, u.username as author FROM notes n LEFT JOIN users u ON u.id=n.created_by WHERE n.id=?',
        (note_id,)
    ).fetchone()
    if not note:
        return "Note not found", 404
    notebook = db.execute('SELECT * FROM notebooks WHERE id=?', (note['notebook_id'],)).fetchone()

    # Fetch comments and tags (Sprint 2)
    comments = db.execute(
        'SELECT c.*, u.username FROM comments c LEFT JOIN users u ON c.user_id=u.id WHERE c.note_id=? ORDER BY c.timestamp ASC',
        (note_id,)
    ).fetchall()
    tags = db.execute('SELECT tag FROM tags WHERE note_id=?', (note_id,)).fetchall()

    return render_template(
    'note.html',
    note=note,
    notebook=notebook,
    comments=comments,
    tags=tags,
    current_user=current_user(),
    current_year=datetime.datetime.utcnow().year
)

# route for creating a new note
@notebook_bp.route('/note/create', methods=['POST'])
@login_required
def create_note():
    """📝 Create a new note in a notebook."""
    title = request.form.get('title') or 'Untitled'
    notebook_id = request.form.get('notebook_id')
    if not notebook_id or not notebook_id.isdigit():
        return jsonify({'error': 'invalid notebook id'}), 400
    notebook_id = int(notebook_id)
    content = request.form.get('content') or ''
    user = current_user()
    now = datetime.datetime.utcnow().isoformat()
    db = get_db()

    # Create the note
    cur = db.execute(
        '''
        INSERT INTO notes (notebook_id, title, content, created_by, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ''',
        (notebook_id, title, content, user['id'], now, now)
    )
    db.commit()

    # Log contribution with timestamp
    db.execute(
        '''
        INSERT INTO contributions (note_id, user_id, action, detail, timestamp)
        VALUES (?, ?, ?, ?, ?)
        ''',
        (cur.lastrowid, user['id'], 'Created note', f'Title: {title}', datetime.datetime.utcnow())
    )
    db.commit()

    return jsonify({'note_id': cur.lastrowid, 'message': 'note created'})

# route for updating a note

@notebook_bp.route('/note/<int:note_id>', methods=['PUT'])
@login_required
def update_note(note_id):
    """📝 Update an existing note."""
    import datetime
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

    # include timestamp in contributions
    db.execute(
        'INSERT INTO contributions (note_id, user_id, action, detail, timestamp) VALUES (?, ?, ?, ?, ?)',
        (note_id, user['id'], 'Edited note', f'Title: {title}', datetime.datetime.utcnow())
    )
    db.commit()

    return jsonify({'message': 'note updated successfully'})

# route for deleting a note
@notebook_bp.route('/note/<int:note_id>', methods=['DELETE'])
@login_required
def delete_note(note_id):
    """📝 Delete a note."""
    db = get_db()
    note = db.execute('SELECT * FROM notes WHERE id=?', (note_id,)).fetchone()
    if not note:
        return jsonify({'error': 'note not found'}), 404

    user = current_user()
    if note['created_by'] != user['id']:
        return jsonify({'error': 'unauthorized'}), 403

    # Delete the note
    db.execute('DELETE FROM notes WHERE id=?', (note_id,))
    db.commit()

    # Log the deletion with timestamp
    from datetime import datetime
    db.execute(
        'INSERT INTO contributions (note_id, user_id, action, detail, timestamp) VALUES (?, ?, ?, ?, ?)',
        (note_id, user['id'], 'Deleted note', f'Note ID: {note_id}', datetime.utcnow())
    )
    db.commit()

    return jsonify({'message': f'note {note_id} deleted successfully'})


# 🏷️ Add a tag to a note (Sprint 2).
@notebook_bp.route('/note/<int:note_id>/tags', methods=['POST'])
@login_required
def add_tag(note_id):
    tag = (request.form.get('tag') or '').strip()
    if not tag:
        return jsonify({'error': 'empty tag'}), 400
    db = get_db()
    db.execute('INSERT INTO tags (note_id, tag) VALUES (?, ?)', (note_id, tag))
    db.commit()
    return jsonify({'message': f'tag "{tag}" added'})

# 📊 Retrieve all contributions (Sprint 2)
@notebook_bp.route('/contributions', methods=['GET'])
@login_required
def get_contributions():
    db = get_db()
    rows = db.execute("""
        SELECT c.id, c.note_id, c.user_id, c.action, c.detail, c.timestamp, 
               u.username, n.title AS note_title
        FROM contributions c
        LEFT JOIN users u ON c.user_id = u.id
        LEFT JOIN notes n ON c.note_id = n.id
        ORDER BY c.timestamp DESC
    """).fetchall()
    return jsonify([dict(row) for row in rows])

# search and summary routes


# ==========================================================
# === SUMMARIZE NOTE CONTENT USING TEXT-TO-SPEECH (TTS) ===
# ==========================================================

def generate_summary(text):
    print("[LOG] Generating summary...")
    sentences = re.split(r'(?<=[.!?]) +', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) <= 3:
        print("[LOG] Short content, returning full text as summary.")
        return text

    words = re.findall(r'\w+', text.lower())
    freq = {}
    for w in words:
        if len(w) > 3:
            freq[w] = freq.get(w, 0) + 1

    scored = [(sum(freq.get(w, 0) for w in s.lower().split()), s) for s in sentences]
    top_sentences = [s for _, s in sorted(scored, reverse=True)[:5]]
    summary = " ".join(top_sentences).strip()
    print(f"[LOG] Summary generated: {summary[:100]}{'...' if len(summary) > 100 else ''}")
    return summary

# route for summarizing notebook content
@notebook_bp.route('/<int:notebook_id>/summarize', methods=['GET'])
@login_required
def summarize_notebook(notebook_id):
    print(f"[LOG] /summarize called for notebook_id={notebook_id}")
    db = get_db()
    notebook = db.execute('SELECT * FROM notebooks WHERE id=?', (notebook_id,)).fetchone()
    if not notebook:
        print("[ERROR] Notebook not found")
        return jsonify({'error': 'notebook not found'}), 404

    notes = db.execute('SELECT title, content FROM notes WHERE notebook_id=?', (notebook_id,)).fetchall()
    if not notes:
        print("[LOG] No notes found in notebook")
        return jsonify({'summary': "This notebook has no notes."})

    full_text = " ".join(f"{n['title']}. {n['content']}" for n in notes if n['content']).strip()
    if not full_text:
        print("[LOG] Notebook content empty")
        return jsonify({'summary': "Notebook content is empty."})

    summary = generate_summary(full_text)
    print("[LOG] Returning JSON summary")
    return jsonify({'summary': summary})


# ==========================================================
# route for serving summary audio file
@notebook_bp.route('/<int:notebook_id>/summary.mp3', methods=['GET'])
@login_required
def serve_summary_audio(notebook_id):
    """
    Serve a fresh summary MP3 for the notebook.
    - Uses a unique temp file per request to avoid Windows file locking
    - Generates TTS audio on the fly
    """
    print(f"[LOG] 🎧 /summary.mp3 requested for notebook {notebook_id}")
    db = get_db()

    # === Get notebook content ===
    notes = db.execute(
        'SELECT title, content FROM notes WHERE notebook_id=?',
        (notebook_id,)
    ).fetchall()
    if not notes:
        print("[ERROR] No notes to read.")
        return jsonify({'error': 'No notes found.'}), 404

    full_text = " ".join(f"{n['title']}. {n['content']}" for n in notes if n['content']).strip()
    if not full_text:
        print("[ERROR] Notebook content empty.")
        return jsonify({'error': 'Notebook empty.'}), 404

    # === Generate summary ===
    summary = generate_summary(full_text)

    try:
        import tempfile
        import pyttsx3

        # Create a unique temporary file for this request
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=f"_summary_{notebook_id}.mp3")
        os.close(tmp_fd)  # Close the low-level fd

        # Generate TTS audio
        engine = pyttsx3.init()
        engine.save_to_file(summary, tmp_path)
        engine.runAndWait()
        engine.stop()

        # Serve the file directly
        print(f"[LOG] ✅ Serving fresh summary.mp3 for notebook {notebook_id}")
        return send_file(tmp_path, mimetype='audio/mpeg', as_attachment=False)

    except Exception as e:
        print(f"[ERROR] ❌ Failed to generate TTS summary: {e}")
        return jsonify({'error': 'Failed to generate summary audio.'}), 500


#----------------------------------------------------------------#
# DEVELOP COMMENTING FEATURES FOR SPRINT 2
#----------------------------------------------------------------#
# 💬 Add a comment or reply (Sprint 2)
@notebook_bp.route('/note/<int:note_id>/comments', methods=['POST'])
@login_required
def add_comment(note_id):
    user = current_user()
    db = get_db()

    # Support both JSON and form data
    data = request.get_json() or request.form
    content = (data.get('content') or '').strip()
    parent_id = data.get('parent_id')

    if not content:
        return jsonify({'error': 'empty comment'}), 400

    # Ensure parent_id is None if empty string
    if parent_id in ('', None):
        parent_id = None

    db.execute(
        'INSERT INTO comments (note_id, user_id, parent_id, content) VALUES (?, ?, ?, ?)',
        (note_id, user['id'], parent_id, content)
    )
    db.commit()

    # Log contribution (Sprint 2)
    db.execute(
        'INSERT INTO contributions (note_id, user_id, action, detail) VALUES (?, ?, ?, ?)',
        (note_id, user['id'], 'Commented', content[:100])
    )
    db.commit()

    return jsonify({'message': 'comment added'})
# -----------------------------
# Implementing Comment Editing & Deletion (Sprint 2 Enhancement)
# -----------------------------
@notebook_bp.route('/comment/<int:comment_id>', methods=['PUT'])
@login_required
def update_comment(comment_id):
    """💬 Update an existing comment (Sprint 2)."""
    db = get_db()
    user = current_user()
    comment = db.execute(
        'SELECT * FROM comments WHERE id=?', (comment_id,)
    ).fetchone()

    if not comment:
        return jsonify({'error': 'comment not found'}), 404
    if comment['user_id'] != user['id']:
        return jsonify({'error': 'unauthorized'}), 403

    data = request.get_json() or request.form
    new_content = (data.get('content') or '').strip()
    if not new_content:
        return jsonify({'error': 'empty comment'}), 400

    db.execute(
        'UPDATE comments SET content=?, timestamp=CURRENT_TIMESTAMP WHERE id=?',
        (new_content, comment_id)
    )
    db.commit()

    # Log contribution (Sprint 2)
    db.execute(
        'INSERT INTO contributions (note_id, user_id, action, detail) VALUES (?, ?, ?, ?)',
        (comment['note_id'], user['id'], 'Edited comment', new_content[:100])
    )
    db.commit()

    return jsonify({'message': 'comment updated successfully'})

# route for deleting a comment
@notebook_bp.route('/comment/<int:comment_id>', methods=['DELETE'])
@login_required
def delete_comment(comment_id):
    """💬 Delete a comment (Sprint 2)."""
    db = get_db()
    user = current_user()
    comment = db.execute(
        'SELECT * FROM comments WHERE id=?', (comment_id,)
    ).fetchone()

    if not comment:
        return jsonify({'error': 'comment not found'}), 404
    if comment['user_id'] != user['id']:
        return jsonify({'error': 'unauthorized'}), 403

    db.execute('DELETE FROM comments WHERE id=?', (comment_id,))
    db.commit()

    # Log contribution (Sprint 2)
    db.execute(
        'INSERT INTO contributions (note_id, user_id, action, detail) VALUES (?, ?, ?, ?)',
        (comment['note_id'], user['id'], 'Deleted comment', f'Comment ID: {comment_id}')
    )
    db.commit()

    return jsonify({'message': 'comment deleted successfully'})


# ==========================================================
# Sprint 3
#--------------------------------------------------------------------------------------------------#
# 🔍 Search notes within all notebooks. 
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
                results.append({
                    'notebook_id': nb['id'],
                    'note_id': note['id'],
                    'note_title': note['title'],
                    'snippet': snippet
                })
    return jsonify(results)


#=================================================================================================#
# AI assisted note generation 
#=================================================================================================#
import language_tool_python
# Initialize local AI/text tool
tool = language_tool_python.LanguageTool('en-US')

@notebook_bp.route('/<int:notebook_id>/add_note', methods=['POST'])
@login_required
def add_note(notebook_id):
    print(f"[LOG] /add_note called for notebook_id={notebook_id}")

    db = get_db()
    notebook = db.execute('SELECT * FROM notebooks WHERE id=?', (notebook_id,)).fetchone()
    if not notebook:
        print("[ERROR] Notebook not found")
        return jsonify({'error': 'Notebook not found'}), 404

    data = request.get_json()
    content = (data.get('content') or "").strip()
    if not content:
        print("[ERROR] No note content provided")
        return jsonify({'error': 'No content provided'}), 400

    # --- AI-assisted enhancement ---
    try:
        matches = tool.check(content)
        enhanced_content = language_tool_python.utils.correct(content, matches)
        print("[LOG] Note content enhanced using local AI tool")
    except Exception as e:
        print(f"[WARN] AI enhancement failed, saving original note. Error: {e}")
        enhanced_content = content

    user = current_user()
    now = datetime.datetime.utcnow().isoformat()

    # Add required fields created_at, updated_at, created_by
    db.execute(
        '''
        INSERT INTO notes (notebook_id, title, content, created_by, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ''',
        (notebook_id, 'Voice Note', enhanced_content, user['id'], now, now)
    )
    db.commit()

    print(f"[LOG] ✅ Note added successfully to notebook {notebook_id}")
    return jsonify({'success': True, 'message': 'Note added successfully.'})

#=================================================================================================#
# -----------------------------
# SSE: Real-time Note Change Notifications # Sprint 3
# -----------------------------
# Dictionary to hold subscribers for each notebook

def notify_notebook_change(notebook_id, note_data):
    """
    Push note_data to all SSE subscribers of a notebook.
    note_data: dict containing 'action', 'note_id', 'content', etc.
    """
    if notebook_id in notebook_subscribers:
        for q in notebook_subscribers[notebook_id]:
            q.append(note_data)

@notebook_bp.route('/<int:notebook_id>/subscribe')
@login_required
def subscribe_notebook(notebook_id):
    """
    SSE endpoint for real-time notebook updates.
    Clients can listen to this to get live updates when notes are added/updated.
    """
    def event_stream():
        if notebook_id not in notebook_subscribers:
            notebook_subscribers[notebook_id] = []

        q = []
        notebook_subscribers[notebook_id].append(q)

        try:
            while True:
                if q:
                    data = q.pop(0)
                    yield f"data: {json.dumps(data)}\n\n"
                time.sleep(0.5)
        except GeneratorExit:
            notebook_subscribers[notebook_id].remove(q)

    return Response(stream_with_context(event_stream()), mimetype="text/event-stream")

# -----------------------------
#  Add Note (with SSE notification)
# -----------------------------
@notebook_bp.route('/<int:notebook_id>/add_note', methods=['POST'], endpoint='add_note_sse')
@login_required
def add_note_sse(notebook_id):
    """
    Add a new note and notify subscribers in real-time.
    """
    db = get_db()
    notebook = db.execute('SELECT * FROM notebooks WHERE id=?', (notebook_id,)).fetchone()
    if not notebook:
        return jsonify({'error': 'Notebook not found'}), 404

    data = request.get_json()
    content = (data.get('content') or "").strip()
    if not content:
        return jsonify({'error': 'No content provided'}), 400

    user = current_user()
    now = datetime.datetime.utcnow().isoformat()

    cur = db.execute(
        '''
        INSERT INTO notes (notebook_id, title, content, created_by, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ''',
        (notebook_id, 'Voice Note', content, user['id'], now, now)
    )
    db.commit()

    # SSE notification
    notify_notebook_change(notebook_id, {
        'action': 'note_added',
        'note_id': cur.lastrowid,
        'content': content,
        'created_by': user['username'],
        'timestamp': now
    })

    return jsonify({'success': True, 'message': 'Note added successfully.'})
# -----------------------------
#  Update Note (with Server-Sent Events (SSE) notification)
# -----------------------------
@notebook_bp.route('/note/<int:note_id>', methods=['PUT'], endpoint='update_note_sse')
@login_required
def update_note_sse(note_id):
    """
    Update an existing note and notify subscribers in real-time.
    """
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

    # SSE notification
    notify_notebook_change(note['notebook_id'], {
        'action': 'note_updated',
        'note_id': note_id,
        'title': title,
        'content': content,
        'updated_by': user['username'],
        'timestamp': now
    })

    return jsonify({'message': 'note updated successfully'})
