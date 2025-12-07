import os
import unittest
import tempfile
import sqlite3
from app import app
import database                     # Import database module to patch DATABASE variable
from database import get_db, init_db


class NoteBridgeTestCase(unittest.TestCase):

    def setUp(self):
        # Create temporary SQLite DB
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")

        # Configure test app
        app.config["TESTING"] = True
        app.config["DATABASE"] = self.db_path
        app.config["WTF_CSRF_ENABLED"] = False
        app.config["SECRET_KEY"] = "test-key"

        # Patch DATABASE inside database.py module
        database.DATABASE = self.db_path

        self.client = app.test_client()

        # Initialize clean DB
        with app.app_context():
            db = get_db()
            init_db(db)

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_index_page(self):
        rv = self.client.get("/")
        self.assertEqual(rv.status_code, 200)

    def test_register_page(self):
        rv = self.client.get("/register")
        self.assertEqual(rv.status_code, 200)
        self.assertIn(b"Register", rv.data)

    def test_login_page(self):
        rv = self.client.get("/login")
        self.assertEqual(rv.status_code, 200)
        self.assertIn(b"Login", rv.data)

    def test_register_and_login(self):
        # Register user (Flask-WTF sometimes needs 'submit')
        rv = self.client.post("/register", data={
            "username": "testuser",
            "password": "testpass",
            "full_name": "Test User",
            "submit": "Register"
        }, follow_redirects=True)

        self.assertEqual(rv.status_code, 200, rv.data)

        # Login
        rv = self.client.post("/login", data={
            "username": "testuser",
            "password": "testpass",
            "submit": "Login"
        }, follow_redirects=True)

        self.assertEqual(rv.status_code, 200)
        self.assertIn(b"Dashboard", rv.data)

    def test_create_and_view_notebook(self):
        # Register
        self.client.post("/register", data={
            "username": "user1",
            "password": "pass1",
            "full_name": "User One",
            "submit": "Register"
        }, follow_redirects=True)

        # Login
        self.client.post("/login", data={
            "username": "user1",
            "password": "pass1",
            "submit": "Login"
        }, follow_redirects=True)

        # Create notebook
        rv = self.client.post("/notebook/create", data={
            "title": "MyFirstNB",
            "submit": "Create"
        }, follow_redirects=True)

        self.assertEqual(rv.status_code, 200)
        self.assertIn(b"MyFirstNB", rv.data)

        # View notebooks
        rv = self.client.get("/notebook/notebooks")
        self.assertEqual(rv.status_code, 200)
        self.assertIn(b"MyFirstNB", rv.data)

    def test_db_connection_close(self):
        with app.app_context():
            db = get_db()
            db2 = get_db()
            self.assertIs(db, db2)

            # store for checking after closing
            stored = db

        # After context ends, DB should be closed
        with self.assertRaises(sqlite3.ProgrammingError):
            stored.execute("SELECT 1")


if __name__ == "__main__":
    unittest.main()
