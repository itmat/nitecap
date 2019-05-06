import os
from datetime import timedelta

DEBUG = True
ENV='development'
DATABASE_FILE = os.environ['DATABASE_FILE']
DATABASE_FOLDER = os.environ.get('DATABASE_FOLDER','')
if DATABASE_FOLDER:
    DATABASE_FOLDER += os.sep
DATABASE = DATABASE_FOLDER + DATABASE_FILE
SQLALCHEMY_DATABASE_URI = "sqlite:///" + DATABASE
SQLALCHEMY_TRACK_MODIFICATIONS = False
JSONIFY_PRETTYPRINT_REGULAR = False
PROPAGATE_EXCEPTIONS = True
MAX_CONTENT_LENGTH = 40 * 1024 * 1024
SECRET_KEY = os.environ["SECRET_KEY"]
SMTP_SERVER_HOST = os.environ['SMTP_SERVER_HOST']
ADMIN_LIST = os.environ.get('ADMINS','').split(",")
PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)