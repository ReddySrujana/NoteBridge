import os

DATABASE = os.path.join(os.path.dirname(__file__), 'notebridge.db')
SECRET_KEY = os.environ.get('SECRET_KEY', 'qwerty1234')
DEBUG = True
