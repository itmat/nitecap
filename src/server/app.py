#!/usr/bin/env python
import os

from flask import Flask, render_template, request, redirect, url_for, jsonify
import werkzeug
import json

from db import db
import logging
from momentjs import momentjs
from logging.handlers import RotatingFileHandler
from pythonjsonlogger import jsonlogger

# Load environment variables (for local development)
if os.environ["ENV"] == "DEV":
    with open("outputs.json") as outputs:
        outputs = json.load(outputs)

    for stack in outputs:
        if stack.endswith("ServerStack"):
            outputs = outputs[stack]

    for variable in outputs["EnvironmentVariables"].split():
        if variable not in os.environ:
            os.environ[variable] = outputs[variable.replace("_", "")]

    if "SECRET_KEY" not in os.environ:
        os.environ["SECRET_KEY"] = "SECRET_KEY"

app = Flask(__name__)
app.config.from_object('config_default')
app.jinja_env.globals['momentjs'] = momentjs
app.jinja_env.globals['ENV'] = app.config['ENV']

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

# File logger - rotates for every 5 MB up to 10 files.
# Applied to the root logger, so this catches all logging
file_handler = RotatingFileHandler(os.environ["LOGS_DIRECTORY_PATH"]+"/application.log", maxBytes=5_000_000, backupCount=10)
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

    if os.environ["ENV"] == "DEV":
        # Create a test user with the specified username+password (both "testuser")
        from models.users.user import User
        user, _, _ = User.register_user("testuser", "testuser@nitecap.org", "testuser")
        if not user.activated:
            user.activated = 1
            user.save_to_db()


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

if __name__ == '__main__':
    app.logger.info("Starting app")
    db.init_app(app)
    app.run(host='0.0.0.0')
