import json
import datetime
import secrets

from sqlalchemy import orm

from db import db
from models.users.user import User
from flask import current_app

TOKEN_SIZE = 75 # bytes

class Share(db.Model):
    __tablename__ = 'shares'
    id = db.Column(db.String(100), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    #user = db.relationship("User")
    spreadsheet_ids_str = db.Column(db.String(250), nullable=False) #comma-separated list of integer spreadsheet ids
    config_json = db.Column(db.String(500), nullable=False)
    date_shared = db.Column(db.DateTime, nullable=False)
    last_access = db.Column(db.DateTime, nullable=False)

    def __init__(self, spreadsheet_ids, user_id, config, id=None, date_shared=None, last_access=None):
        '''
        Share objects grant access to particular spreadsheet(s) from a given user
        so that they can be viewed by others.
        :param spreadsheet_ids: list of spreadsheet ids to grant access to
        :param user_id: user id of the user owning the spreadsheets
        :param config: dictionary of front-end configuration values
        :param date_shared: Date the share was created
        :param last_access: Date of last access to the share
        '''
        self.user_id = user_id
        self.spreadsheet_ids_str = ','.join(str(id) for id in spreadsheet_ids)
        self.date_shared = date_shared or datetime.datetime.utcnow()
        self.last_access = last_access or datetime.datetime.utcnow()
        self.config_json = json.dumps(config)


        if id is not None:
            self.id = id
        else:
            self.id = secrets.token_urlsafe(TOKEN_SIZE)

    def save_to_db(self):
        """
        Save the Share to the database and note the current time as the last modified time in the
        database.
        """
        self.last_access = datetime.datetime.utcnow()
        db.session.add(self)
        db.session.commit()

    @classmethod
    def find_by_id(cls, _id):
        return cls.query.filter_by(id=_id).first()
