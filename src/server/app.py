#!/usr/bin/env python
import smtplib
import sys

# create the necessary directories and files, if needed
import os
os.makedirs("/storage/uploads", exist_ok=True)
os.makedirs("/storage/db_backup", exist_ok=True)
os.makedirs("/storage/db", exist_ok=True)

from pathlib import Path
Path("/storage/log").touch()

from email.message import EmailMessage

from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv, find_dotenv
from flask import Flask, render_template, request, redirect, url_for, jsonify
import werkzeug
import json
# Uncomment to allow CORS
#from flask_cors import CORS

from db import db
from apscheduler.schedulers.background import BackgroundScheduler
import backup
import visitor_purge
import logging
import os
from momentjs import momentjs
from logging.handlers import RotatingFileHandler, SMTPHandler
from models.users.decorators import requires_admin, ajax_requires_admin

logger = logging.getLogger("")

app = Flask(__name__)
load_dotenv(find_dotenv(usecwd=True))
app.config.from_object('config_default')
app.config.from_envvar('APPLICATION_SETTINGS')
app.jinja_env.globals['momentjs'] = momentjs
#CORS(app, resources=r'/spreadsheets/*', headers='Content-Type')

# Log format for both file and email logging.
formatter = logging.Formatter('%(asctime)s \t%(levelname)s\t%(module)s\t%(process)d\t%(thread)d\t%(message)s')

# Email logger - assumes the existence of at least 1 admin email.
mail_handler = SMTPHandler(
    mailhost=os.environ['SMTP_SERVER_HOST'],
    fromaddr=os.environ['EMAIL_SENDER'],
    toaddrs=app.config['ADMIN_LIST'],
    subject='Nitcap Application Issue'
)
mail_handler.setLevel(logging.WARN)
mail_handler.setFormatter(formatter)

# File logger - rotates for every 1Mb up to 10 files.
file_handler = RotatingFileHandler(os.environ["LOG_FILE"], maxBytes=1_000_000, backupCount=10)
file_handler.setLevel(os.environ.get('LOG_LEVEL', logging.WARN))
file_handler.setFormatter(formatter)
logger.setLevel(os.environ.get('LOG_LEVEL', logging.WARN))
logger.addHandler(file_handler)

# Email warning and errors only for production server
#if not app.debug:
#    app.logger.addHandler(mail_handler)

# Catch exceptions and log them
@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.error("Exception received:")
    app.logger.error(e)
    raise e

@app.errorhandler(404)
def handle_404(e):
    errors = ["URL not found"]
    return render_template("home.html", errors=errors), 404

# Check python version and paths:
logger.debug("Python version")
logger.debug(sys.version)
logger.debug("Python paths")
for python_path in sys.path:
    logger.debug(python_path)

@app.before_first_request
def create_tables():
    db.create_all()

# @app.before_request
# def check_session():
#     print(session)


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

@app.route('/gallery', methods=['GET'])
def gallery():
    # load the gallery shares
    with open("static/json/gallery_shares.json") as gallery_json:
        gallery = json.load(gallery_json)
    return render_template("gallery.html",
                gallery=gallery)


@app.route('/dashboard', methods=['GET'])
@requires_admin
def dashboard():
    return redirect(url_for('users.display_users'))

@app.route('/send_feeedback', methods=['POST'])
def send_feedback():
    json_data = request.get_json()
    comments = json_data.get('comments', None)
    if comments:
        print(comments)
        email = EmailMessage()
        email['Subject'] = 'Nitecap Feedback'
        email['From'] = os.environ.get('EMAIL_SENDER')
        email['To'] = os.environ.get('EMAIL_SENDER')
        email.set_content(comments)
        try:
            s = smtplib.SMTP(host=os.environ.get('SMTP_SERVER_HOST'), port=25)
            s.send_message(email)
            s.quit()
        except Exception as e:
            app.logger.error(f"Email delivery failed: {e}")
            return jsonify({'error': 'Unable to deliver feedback.  Please try again later.'}), 500
    return '', 204


@app.errorhandler(413)
@app.errorhandler(werkzeug.exceptions.RequestEntityTooLarge)
def file_too_large(e):
    app.logger.warning("Too large a file was attempted to be uploaded")
    app.logger.warning(e)
    max_size = app.config['MAX_CONTENT_LENGTH'] // (1024*1024)
    errors = [f"Uploaded file was too large. Maximum size is {max_size} MB"]
    return render_template('spreadsheets/upload_file.html', errors=errors), 413


from models.users.views import user_blueprint
from models.spreadsheets.views import spreadsheet_blueprint
app.register_blueprint(user_blueprint, url_prefix='/users')
app.register_blueprint(spreadsheet_blueprint, url_prefix='/spreadsheets')


def db_backup_job():
    logger.info('Database backup underway.')
    backup.backup(app.config['DATABASE'])
    backup.clean_backups()
    logger.info('Database backup complete.')


def visitor_purge_job():
    logger.info('Visitor purge underway.')
    ids = visitor_purge.purge(True, app.config['DATABASE'])
    if ids:
        logger.info(f"Visitor ids: {','.join(ids)} removed along with data and files.")
    else:
        logger.info(f"No old visitor spreadsheets were found.")
    logger.info('Visitor spreadsheet purge complete.')


scheduler = BackgroundScheduler()
db_job = scheduler.add_job(db_backup_job, CronTrigger.from_crontab('5 0 * * *'))
spreadsheet_job = scheduler.add_job(visitor_purge_job, CronTrigger.from_crontab('5 1 * * *'))
scheduler.start()


import computation.api
import computation.example


if __name__ == '__main__':
    db.init_app(app)
    app.run(host='0.0.0.0')
