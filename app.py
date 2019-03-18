import sched

from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv, find_dotenv
from flask import Flask, render_template, request, session, flash, redirect, url_for
from db import db
from apscheduler.schedulers.background import BackgroundScheduler
import backup
import logging
import os
from momentjs import momentjs
from logging.handlers import RotatingFileHandler

logger = logging.getLogger("")

app = Flask(__name__)
load_dotenv(find_dotenv(usecwd=True))
app.config.from_object('config_default')
app.config.from_envvar('APPLICATION_SETTINGS')
app.jinja_env.globals['momentjs'] = momentjs

@app.before_first_request
def create_tables():
    db.create_all()
    handler = RotatingFileHandler(os.environ["LOG_FILE"], maxBytes=1_000_000, backupCount=10)
    handler.setLevel(os.environ.get('LOG_LEVEL', logging.WARN))
    formatter = logging.Formatter('%(asctime)s : %(levelname)s : %(message)s')
    handler.setFormatter(formatter)
    logger.setLevel(os.environ.get('LOG_LEVEL', logging.WARN))
    logger.addHandler(handler)

@app.route('/', methods=['GET'])
def home():
    logger.info("Accessing home")
    return render_template("home.html")

@app.route('/faqs', methods=['GET'])
def faqs():
    return render_template("faqs.html")

@app.route('/people', methods=['GET'])
def people():
    return render_template("people.html")

@app.errorhandler(413)
def file_to_large(e):
    messages = ["The file you are attempting to upload is too large for the site to accommodate."]
    return render_template('spreadsheets/spreadsheet_upload_form.html', messages=messages), 413

from models.users.views import user_blueprint
from models.confirmations.views import confirmation_blueprint
from models.spreadsheets.views import spreadsheet_blueprint
app.register_blueprint(user_blueprint, url_prefix='/users')
app.register_blueprint(confirmation_blueprint, url_prefix='/confirmations')
app.register_blueprint(spreadsheet_blueprint, url_prefix='/spreadsheets')

def db_backup_job():
    backup.backup(app.config['DATABASE'])
    backup.clean_backups()
    print('Backup process completed')

scheduler = BackgroundScheduler()
job = scheduler.add_job(db_backup_job, CronTrigger.from_crontab('5 0 * * *'))
scheduler.start()

if __name__ == '__main__':
    db.init_app(app)
    app.run(host='0.0.0.0')
