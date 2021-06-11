#!/usr/bin/env python
import boto3
import os

# Retrieve the secret key
SECRET_KEY_ARN = os.environ["SERVER_SECRET_KEY_ARN"]
SECRET_VALUE = boto3.client("secretsmanager").get_secret_value(SecretId=SECRET_KEY_ARN)
os.environ["SECRET_KEY"] = SECRET_VALUE["SecretString"]

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
from pythonjsonlogger import jsonlogger
from models.users.decorators import requires_admin, ajax_requires_admin

app = Flask(__name__)
load_dotenv(find_dotenv(usecwd=True))
app.config.from_object('config_default')
app.config.from_envvar('APPLICATION_SETTINGS')
app.jinja_env.globals['momentjs'] = momentjs
app.jinja_env.globals['ENV'] = app.config['ENV']
#CORS(app, resources=r'/spreadsheets/*', headers='Content-Type')

class ReverseProxied:
    """
    Force the use of 'https' in urls where appropriate
    since the reverse proxy will make it look like we are receiving http
    """
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app
    def __call__(self, environ, start_response):
        if app.config['USE_HTTPS']:
            environ['wsgi.url_scheme'] = "https"
        return self.wsgi_app(environ, start_response)
app.wsgi_app = ReverseProxied(app.wsgi_app)

# Log format
# formatter = logging.Formatter('%(asctime)s \t%(levelname)s\t%(module)s\t%(process)d\t%(thread)d\t%(message)s')
formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(module)s %(process)d %(thread)d %(message)s')

# Root logger - catches all logging
# Anything logged by app.logger will also go through Flasks default stream (i.e. stderr) logging
# (In prod, the stream logging gets redirected to the error log file in the apache conf file apache/nitecap.conf)
logger = logging.getLogger("")

# File logger - rotates for every 1Mb up to 10 files.
# Applied to the root logger, so this catches all logging
file_handler = RotatingFileHandler(os.environ["LOGS_DIRECTORY_PATH"]+"/application.log", maxBytes=1_000_000, backupCount=10)
file_handler.setLevel(os.environ.get('LOG_LEVEL', logging.WARN))
file_handler.setFormatter(formatter)
logger.setLevel(os.environ.get('LOG_LEVEL', logging.WARN))
logger.addHandler(file_handler)

@app.errorhandler(404)
def handle_404(e):
    errors = ["URL not found"]
    return render_template("home.html", errors=errors), 404

@app.before_first_request
def create_tables():
    db.create_all()


@app.route('/', methods=['GET'])
def home():
    return render_template("home.html")


@app.route('/faqs', methods=['GET'])
def faqs():
    app.logger.info("Accessing faqs")
    return render_template("faqs.html")


@app.route('/about', methods=['GET'])
def about():
    app.logger.info("Accessing about page")
    return render_template("about.html")

@app.route('/gallery', methods=['GET'])
def gallery():
    app.logger.info("Accessing gallery")
    # load the gallery shares
    with open("static/json/gallery_shares.json") as gallery_json:
        gallery = json.load(gallery_json)
    return render_template("gallery.html",
                gallery=gallery)

@app.route('/user_guide', methods=['GET'])
def user_guide():
    return render_template("user_guide.html")


@app.route('/dashboard', methods=['GET'])
@requires_admin
def dashboard():
    return redirect(url_for('users.display_users'))

@app.errorhandler(413)
@app.errorhandler(werkzeug.exceptions.RequestEntityTooLarge)
def file_too_large(e):
    app.logger.warning(e, exc_info=True)
    max_size = app.config['MAX_CONTENT_LENGTH'] // (1024*1024)
    errors = [f"Uploaded file was too large. Maximum size is {max_size} MB"]
    return jsonify({"errors": errors}), 413


from models.users.views import user_blueprint
from models.spreadsheets.views import spreadsheet_blueprint
app.register_blueprint(user_blueprint, url_prefix='/users')
app.register_blueprint(spreadsheet_blueprint, url_prefix='/spreadsheets')

from computation.api import analysis_blueprint
app.register_blueprint(analysis_blueprint, url_prefix='/analysis')

#TODO: Remove this in production
from computation.example import computation_test_blueprint
app.register_blueprint(computation_test_blueprint, url_prefix='/computation')

def db_backup_job():
    app.logger.info('Database backup underway.')
    backup.backup(app.config['DATABASE'])
    backup.clean_backups()
    app.logger.info('Database backup complete.')


def visitor_purge_job():
    app.logger.info('Visitor purge underway.')
    # TODO: this visitor purge is only in rehearse=True mode
    # and so it does nothing. It needs to be updated to the new backend code
    # and then enabled to run for real
    ids = visitor_purge.purge(True, app.config['DATABASE'])
    if ids:
        app.logger.info(f"Visitor ids: {','.join(ids)} removed along with data and files.")
    else:
        app.logger.info(f"No old visitor spreadsheets were found.")
    app.logger.info('Visitor spreadsheet purge complete.')


scheduler = BackgroundScheduler()
db_job = scheduler.add_job(db_backup_job, CronTrigger.from_crontab('5 0 * * *'))
spreadsheet_job = scheduler.add_job(visitor_purge_job, CronTrigger.from_crontab('5 1 * * *'))
scheduler.start()

if __name__ == '__main__':
    app.logger.info("Starting app")
    db.init_app(app)
    app.run(host='0.0.0.0')
