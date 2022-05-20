import os
from datetime import timedelta

DEBUG = True
ENV = 'production' if os.environ.get("ENV", "PROD") == "PROD" else "development"
DEBUG = (ENV == "development")
DATABASE_FILE = os.environ['DATABASE_FILE']
DATABASE_FOLDER = os.environ.get('DATABASE_FOLDER', '')
if DATABASE_FOLDER:
    DATABASE_FOLDER += os.sep
DATABASE = DATABASE_FOLDER + DATABASE_FILE
SQLALCHEMY_DATABASE_URI = "sqlite:///" + DATABASE
SQLALCHEMY_TRACK_MODIFICATIONS = False
JSONIFY_PRETTYPRINT_REGULAR = False
PROPAGATE_EXCEPTIONS = True
MAX_CONTENT_LENGTH = 80 * 1024 * 1024
SECRET_KEY = os.environ["SECRET_KEY"]
SMTP_SERVER_HOST = os.environ['SMTP_SERVER_HOST']
ADMIN_LIST = os.environ.get('ADMINS', '').split(",")
PERMANENT_SESSION_LIFETIME = timedelta(days=31)
BANNER_CONTENT = os.environ.get('BANNER_CONTENT', '')
BANNER_VISIBLE = bool(os.environ.get('BANNER_VISIBLE', ''))
SESSION_COOKIE_SAMESITE='Lax'
USE_HTTPS = (ENV == 'production')

# For job system
NUM_JOB_WORKERS = 2
JOB_TIMEOUT = 30 * 60 # Seconds
JOB_DROP_TIME = 24 * 60 * 60 # Seconds
