import sys
import os
sys.path.append('/var/www/flask_apps/nitecap')

from app import app as application
from db import db
db.init_app(application)

if __name__=="__main__":
    #application.secret_key = os.environ["SECRET_KEY"]
    #application.debug = bool(os.environ.get("DEBUG", 'False'))
    application.run()