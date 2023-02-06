import os
import json
from datetime import timedelta

database = json.loads(os.environ["DATABASE_SECRET"])

ENV = os.environ.get("ENV", "PROD")
DEBUG = (ENV == "DEV")
SQLALCHEMY_DATABASE_URI = f"postgresql+psycopg://{database['username']}:{database['password']}@{database['host']}:{database['port']}/{database['dbname']}"
SQLALCHEMY_TRACK_MODIFICATIONS = False
JSONIFY_PRETTYPRINT_REGULAR = False
PROPAGATE_EXCEPTIONS = True
MAX_CONTENT_LENGTH = 80 * 1024 * 1024
SECRET_KEY = os.environ["SECRET_KEY"]
PERMANENT_SESSION_LIFETIME = timedelta(days=31)
BANNER_CONTENT = os.environ.get('BANNER_CONTENT', '')
BANNER_VISIBLE = bool(os.environ.get('BANNER_VISIBLE', ''))
SESSION_COOKIE_SAMESITE='Lax'
USE_HTTPS = (ENV == 'PROD')
