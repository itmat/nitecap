import json
import datetime
import secrets
import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from db import db

TOKEN_SIZE = 75 # bytes

class Share(db.Model):
    __tablename__ = 'shares'
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(db.ForeignKey("users.id"))
    spreadsheet_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=False)))
    config_json: Mapped[str] = mapped_column(String(500))
    date_shared: Mapped[datetime.datetime]
    last_access: Mapped[datetime.datetime]

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
        self.spreadsheet_ids = spreadsheet_ids
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

    def delete(self):
        """
        Remove this spreadsheet from the database
        """
        db.session.delete(self)
        db.session.commit()

    @classmethod
    def find_by_id(cls, _id):
        return cls.query.filter_by(id=_id).first()
