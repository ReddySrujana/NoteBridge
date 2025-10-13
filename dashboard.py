from flask import Blueprint, render_template, jsonify
from auth import login_required, current_user
from database import get_db

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    user = current_user()
    db = get_db()

    notebooks = db.execute(
        'SELECT id, title FROM notebooks WHERE owner_id=?', 
        (user['id'],)
    ).fetchall()

    shared_notebooks = db.execute(
        'SELECT n.id, n.title FROM notebooks n '
        'JOIN group_members gm ON gm.user_id=? '
        'JOIN groups g ON g.id=gm.group_id '
        'WHERE n.is_shared=1', 
        (user['id'],)
    ).fetchall()

    groups = db.execute(
        'SELECT g.id, g.name, '
        '(SELECT COUNT(*) FROM group_members gm WHERE gm.group_id=g.id) AS members '
        'FROM groups g'
    ).fetchall()

    return render_template(
        'dashboard.html',
        user=user,
        notebooks=notebooks,
        shared_notebooks=shared_notebooks,
        groups=groups
    )

@dashboard_bp.route('/get_notes_text/<int:note_id>')
@login_required
def get_notes_text(note_id):
    db = get_db()
    note = db.execute(
        'SELECT title, content FROM notes WHERE id=?',
        (note_id,)
    ).fetchone()
    if not note:
        return jsonify({'error': 'Note not found'}), 404
    return jsonify({'notes_text': note['content'], 'title': note['title']})

@dashboard_bp.route('/get_dashboard_text')
@login_required
def get_dashboard_text():
    user = current_user()
    db = get_db()

    notebooks = db.execute(
        'SELECT title FROM notebooks WHERE owner_id=?',
        (user['id'],)
    ).fetchall()

    groups = db.execute(
        'SELECT g.name, '
        '(SELECT COUNT(*) FROM group_members gm WHERE gm.group_id=g.id) AS members '
        'FROM groups g'
    ).fetchall()

    lines = [f"Welcome {user['full_name'] or user['username']}!"]

    if notebooks:
        lines.append("Your notebooks:")
        for nb in notebooks:
            lines.append(nb['title'])
    else:
        lines.append("No notebooks yet.")

    if groups:
        lines.append("Your groups:")
        for g in groups:
            lines.append(f"{g['name']} with {g['members']} members")
    else:
        lines.append("No groups yet.")

    return jsonify({'dashboard_text': "\n".join(lines)})
