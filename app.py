import sched

from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv, find_dotenv
from flask import Flask, render_template, request, session, flash, redirect, url_for
from db import db
from apscheduler.schedulers.background import BackgroundScheduler
import backup
import spreadsheet_purge
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

handler = RotatingFileHandler(os.environ["LOG_FILE"], maxBytes=1_000_000, backupCount=10)
handler.setLevel(os.environ.get('LOG_LEVEL', logging.WARN))
formatter = logging.Formatter('%(asctime)s \t%(levelname)s\t%(module)s\t%(process)d\t%(thread)d\t%(message)s')
handler.setFormatter(formatter)
logger.setLevel(os.environ.get('LOG_LEVEL', logging.WARN))
logger.addHandler(handler)

@app.before_first_request
def create_tables():
    db.create_all()

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

@app.route('/about', methods=['GET'])
def about():
    return render_template("about.html")

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
    logger.info('Database backup underway.')
    backup.backup(app.config['DATABASE'])
    backup.clean_backups()
    logger.info('Database backup complete.')

def anonymous_spreadsheet_purge_job():
    logger.info('Visitor spreadsheet purge underway.')
    ids = spreadsheet_purge.purge(app.config['DATABASE'])
    if ids:
        logger.info(f"Visitor spreadsheet ids: {(',').join(ids)} removed along with files.")
    else:
        logger.info(f"No old visitor spreadsheets were found.")
    logger.info('Visitor spreadsheet purge complete.')

scheduler = BackgroundScheduler()
db_job = scheduler.add_job(db_backup_job, CronTrigger.from_crontab('5 0 * * *'))
spreadsheet_job = scheduler.add_job(anonymous_spreadsheet_purge_job, CronTrigger.from_crontab('5 1 * * *'))
scheduler.start()

if __name__ == '__main__':
    db.init_app(app)
    app.run(host='0.0.0.0')
