#!/usr/bin/env python
import app
from db import db
from models.spreadsheets.spreadsheet import Spreadsheet

db.init_app(app.app)

with app.app.app_context():
    for spreadsheet in db.session.query(Spreadsheet).order_by(Spreadsheet.id):
        print(f"Spreadsheet ID {spreadsheet.id} from user {spreadsheet.user_id}: {spreadsheet.descriptive_name}")