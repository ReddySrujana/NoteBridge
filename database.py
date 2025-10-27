import sqlite3
from flask import g
from config import DATABASE

def get_db():
    """Get or create a database connection for the current Flask request context."""
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

def close_connection(exception=None):
    """Close the database connection when the app context ends."""
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()

def init_db(db):
    """
    Initialize the SQLite database schema for NoteBridge.
    Includes Sprint 2 updates: contributions, tags, comments tables.
    """
    schema = """
    PRAGMA foreign_keys = ON;

    -- USERS TABLE
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT,
        created_at TEXT NOT NULL
    );

    -- GROUPS TABLE
    CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        created_at TEXT NOT NULL
    );

    -- GROUP MEMBERS
    CREATE TABLE IF NOT EXISTS group_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        role TEXT DEFAULT 'member',
        joined_at TEXT NOT NULL,
        FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    -- NOTEBOOKS TABLE
    CREATE TABLE IF NOT EXISTS notebooks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        created_at TEXT NOT NULL,
        is_shared INTEGER DEFAULT 0,
        FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
    );

    -- NOTES TABLE
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

    -- CONTRIBUTIONS TABLE (Sprint 2)
    CREATE TABLE IF NOT EXISTS contributions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        note_id INTEGER NOT NULL,
        user_id INTEGER,
        action TEXT NOT NULL,
        detail TEXT,
        timestamp TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(note_id) REFERENCES notes(id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
    );

    -- TAGS TABLE (Sprint 2)
    CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        note_id INTEGER NOT NULL,
        tag TEXT NOT NULL,
        FOREIGN KEY(note_id) REFERENCES notes(id) ON DELETE CASCADE
    );

    -- COMMENTS TABLE (Sprint 2)
    CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        note_id INTEGER NOT NULL,
        user_id INTEGER,
        parent_id INTEGER,
        content TEXT NOT NULL,
        timestamp TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(note_id) REFERENCES notes(id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL,
        FOREIGN KEY(parent_id) REFERENCES comments(id) ON DELETE CASCADE
    );
    """

    db.executescript(schema)
    db.commit()
