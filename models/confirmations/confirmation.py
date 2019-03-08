from db import db
import uuid
from time import time

CONFIRMATION_EXPIRATION_DELTA = 6 * 60 * 60

class Confirmation(db.Model):
    __tablename__ = "confirmations"

    id = db.Column(db.String(50), primary_key=True)
    expire_at = db.Column(db.Integer, nullable=False)
    confirmed = db.Column(db.Boolean, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    user = db.relationship("User")

    def __init__(self, user_id, **kwargs):
        super().__init__(**kwargs)
        self.user_id = user_id
        self.id = uuid.uuid4().hex
        self.expire_at = int(time()) + CONFIRMATION_EXPIRATION_DELTA
        self.confirmed = False

    @classmethod
    def find_by_id(cls, _id):
        return cls.query.filter_by(id=_id).first()

    @property
    def expired(self):
        return time() > self.expire_at

    def force_to_expire(self):
        if not self.expired:
            self.expire_at = time()
            self.save_to_db()

    def save_to_db(self):
        db.session.add(self)
        db.session.commit()

    def delete_from_db(self):
        db.session.delete(self)
        db.session.commit()





