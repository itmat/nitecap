from flask import Flask, render_template, request, session, flash, redirect, url_for
from db import db

app = Flask(__name__)
app.config.from_object('config')

@app.before_first_request
def create_tables():
    db.create_all()

@app.route('/', methods=['GET'])
def home():
    return redirect(url_for('spreadsheets.load_spreadsheet'))

from models.users.views import user_blueprint
from models.spreadsheets.views import spreadsheet_blueprint
app.register_blueprint(user_blueprint, url_prefix='/users')
app.register_blueprint(spreadsheet_blueprint, url_prefix='/spreadsheets')

if __name__ == '__main__':
    db.init_app(app)
    app.run()
