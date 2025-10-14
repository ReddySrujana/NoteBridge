from flask import Blueprint, render_template, request, redirect, url_for, session, abort
from auth import login_required, current_user
from database import get_db
from werkzeug.security import generate_password_hash
import datetime

group_bp = Blueprint('group', __name__, url_prefix='/groups')

# Helper to get group by ID
def get_group(group_id):
    db = get_db()
    group = db.execute('SELECT * FROM groups WHERE id=?', (group_id,)).fetchone()
    if not group:
        abort(404, "Group not found")
    return group

# Helper to get members of a group
def get_members(group_id):
    db = get_db()
    members = db.execute(
        'SELECT u.id as user_id, u.username, u.full_name, gm.role '
        'FROM users u JOIN group_members gm ON u.id = gm.user_id '
        'WHERE gm.group_id=?',
        (group_id,)
    ).fetchall()
    return members

# POST: Handle group creation (triggered from dashboard form)
@group_bp.route('/create', methods=['POST'])
@login_required
def create_group():
    name = request.form.get('name') or 'New Group'
    description = request.form.get('description', '')
    member_names = request.form.getlist('member_name[]')
    now = datetime.datetime.utcnow().isoformat()
    db = get_db()

    # Insert group
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

    # Add other members if provided
    for uname in member_names:
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
    return redirect(url_for('dashboard.dashboard'))

# View a group
@group_bp.route('/<int:group_id>')
@login_required
def view_group(group_id):
    group = get_group(group_id)
    members = get_members(group_id)
    user = current_user()
    return render_template('group_view.html', group=group, members=members, user=user)

# Edit a group
@group_bp.route('/<int:group_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_group(group_id):
    group = get_group(group_id)
    db = get_db()
    if request.method == 'POST':
        name = request.form.get('name', group['name'])
        description = request.form.get('description', group['description'])
        db.execute('UPDATE groups SET name=?, description=? WHERE id=?', (name, description, group_id))
        db.commit()
        return redirect(url_for('group.view_group', group_id=group_id))

    members = get_members(group_id)
    user = current_user()
    return render_template('group_edit.html', group=group, members=members, user=user)

# Delete a group
@group_bp.route('/<int:group_id>/delete', methods=['POST'])
@login_required
def delete_group(group_id):
    db = get_db()
    db.execute('DELETE FROM group_members WHERE group_id=?', (group_id,))
    db.execute('DELETE FROM groups WHERE id=?', (group_id,))
    db.commit()
    return redirect(url_for('dashboard.dashboard'))

# Add member to group
@group_bp.route('/<int:group_id>/add_member', methods=['POST'])
@login_required
def add_member(group_id):
    username = request.form.get('username')
    role = request.form.get('role', 'member')
    now = datetime.datetime.utcnow().isoformat()
    db = get_db()

    user = db.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()
    if not user:
        cur = db.execute(
            'INSERT INTO users (username, full_name, created_at, password_hash) VALUES (?, ?, ?, ?)',
            (username, username, now, generate_password_hash('defaultpass'))
        )
        user_id = cur.lastrowid
    else:
        user_id = user['id']

    db.execute(
        'INSERT INTO group_members (group_id, user_id, role, joined_at) VALUES (?, ?, ?, ?)',
        (group_id, user_id, role, now)
    )
    db.commit()
    return redirect(url_for('group.view_group', group_id=group_id))

# Remove member from group
@group_bp.route('/<int:group_id>/remove_member/<int:user_id>', methods=['POST'])
@login_required
def remove_member(group_id, user_id):
    db = get_db()
    db.execute('DELETE FROM group_members WHERE group_id=? AND user_id=?', (group_id, user_id))
    db.commit()
    return redirect(url_for('group.view_group', group_id=group_id))

@group_bp.route('', methods=['GET'])
@login_required
def list_groups():
    db = get_db()
    groups = db.execute(
        'SELECT g.id, g.name, '
        '(SELECT COUNT(*) FROM group_members gm WHERE gm.group_id=g.id) AS members '
        'FROM groups g'
    ).fetchall()
    user = current_user()
    # Pass `group=None` so template won't crash
    return render_template('group_view.html', groups=groups, group=None, user=user)

