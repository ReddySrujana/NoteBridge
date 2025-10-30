from flask import Blueprint, redirect, render_template, request, jsonify, url_for
from auth import login_required, current_user
from database import get_db
import datetime
import re
from flask import jsonify, send_file
import pyttsx3
from tempfile import NamedTemporaryFile
from io import BytesIO

notebook_bp = Blueprint('notebook', __name__, url_prefix='/notebook')

# notebook routes

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
    cur = db.execute(
        'INSERT INTO notes (notebook_id, title, content, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)',
        (notebook_id, title, content, user['id'], now, now)
    )
    db.commit()

    # Log contribution (Sprint 2)
    db.execute(
        'INSERT INTO contributions (note_id, user_id, action, detail) VALUES (?, ?, ?, ?)',
        (cur.lastrowid, user['id'], 'Created note', f'Title: {title}')
    )
    db.commit()

    return jsonify({'note_id': cur.lastrowid, 'message': 'note created'})


@notebook_bp.route('/note/<int:note_id>', methods=['PUT'])
@login_required
def update_note(note_id):
    """📝 Update an existing note."""
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

    # Log contribution (Sprint 2)
    db.execute(
        'INSERT INTO contributions (note_id, user_id, action, detail) VALUES (?, ?, ?, ?)',
        (note_id, user['id'], 'Edited note', f'Title: {title}')
    )
    db.commit()

    return jsonify({'message': 'note updated'})


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

    db.execute('DELETE FROM notes WHERE id=?', (note_id,))
    db.commit()

    # Log contribution (Sprint 2)
    db.execute(
        'INSERT INTO contributions (note_id, user_id, action, detail) VALUES (?, ?, ?, ?)',
        (note_id, user['id'], 'Deleted note', f'Note ID: {note_id}')
    )
    db.commit()

    return jsonify({'message': 'note deleted'})


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

# SUMMARIZE NOTE CONTENT USING TEXT-TO-SPEECH

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
    print(f"[LOG] Summary generated: {summary[:100]}{'...' if len(summary)>100 else ''}")
    return summary

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

@notebook_bp.route('/<int:notebook_id>/tts', methods=['GET'])
@login_required
def tts_summary(notebook_id):
    print(f"[LOG] /tts called for notebook_id={notebook_id}")
    db = get_db()
    notebook = db.execute('SELECT * FROM notebooks WHERE id=?', (notebook_id,)).fetchone()
    if not notebook:
        print("[ERROR] Notebook not found")
        return jsonify({'error': 'notebook not found'}), 404
    notes = db.execute('SELECT title, content FROM notes WHERE notebook_id=?', (notebook_id,)).fetchall()
    if not notes:
        print("[ERROR] No notes to read")
        return jsonify({'error': 'No notes to read.'}), 404
    full_text = " ".join(f"{n['title']}. {n['content']}" for n in notes if n['content']).strip()
    if not full_text:
        print("[ERROR] Notebook content empty")
        return jsonify({'error': 'Notebook empty.'}), 404
    summary = generate_summary(full_text)
    print(f"[LOG] Generating TTS for summary (first 100 chars): {summary[:100]}")

    try:
        audio_bytes = BytesIO()
        engine = pyttsx3.init()
        engine.save_to_file(summary, 'summary.mp3')
        engine.runAndWait()
        engine.stop()
        print("[LOG] TTS saved to summary.mp3")

        with open('summary.mp3', 'rb') as f:
            audio_bytes.write(f.read())
        audio_bytes.seek(0)
        print("[LOG] Sending TTS file to client")
        return send_file(audio_bytes, mimetype='audio/mpeg', as_attachment=False, download_name='summary.mp3')
    except Exception as e:
        print("[ERROR] TTS generation failed:", e)
        return jsonify({'error': 'TTS generation failed.'}), 500
    
# Serve the generated summary audio file
@notebook_bp.route('/<int:notebook_id>/summary.mp3', methods=['GET'])
@login_required
def serve_summary_audio(notebook_id):
    import os
    file_path = os.path.join(os.getcwd(), 'summary.mp3')
    if not os.path.exists(file_path):
        print("[ERROR] summary.mp3 not found at", file_path)
        return jsonify({'error': 'Summary audio not found.'}), 404
    print(f"[LOG] Serving summary.mp3 for notebook {notebook_id}")
    return send_file(file_path, mimetype='audio/mpeg', as_attachment=False)

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
