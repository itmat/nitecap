import datetime
import smtplib

from db import db
from email.message import EmailMessage


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False, unique=True)
    email = db.Column(db.String(150), nullable=False, unique=True)
    password = db.Column(db.String(100), nullable=False)
    activated = db.Column(db.Boolean, default=False)
    last_access = db.Column(db.DateTime)


    def __init__(self, username, email, password, activated = False, last_access=None):
        self.username = username
        self.email = email
        self.password = password
        self.activated = activated
        self.last_access = last_access if last_access else datetime.datetime.now()

    def __repr__(self):
        return f"<User id:{self.id}, username: {self.username}, email: {self.email} last acess: {self.last_access}>"

    @staticmethod
    def register_user(username, email, password):
        messages = []
        error = False
        user = User.find_by_email(email)
        if user:
            messages.append("The e-mail you provided is already registered.")
            error = True
            user = None
        else:
            if not username:
                username = email
            user = User.find_by_username(username)
            if user:
                messages.append("The username you provided is already registered.")
                error = True
                user = None
            else:
                user = User(username, email, password)
                user.save_to_db()
                user.send_confirmation_email()
        return user, error, messages

    @staticmethod
    def login_user(username, password):
        messages = []
        error = False
        user = User.find_by_username(username)
        if not user:
            user = User.find_by_email(username)
            if not user:
                messages.append("No such user currently exists in the site.  Please register.")
                error = True
                user = None
        if user:
            if user.password != password:
                messages.append("Invalid credentials.  Try again.")
                error = True
                user = None
            else:
                if user.activated:
                    user.last_access = datetime.datetime.now()
                    user.save_to_db()
                else:
                    messages.append("You need to click on the confirmation link we emailed you before you can login.")
                    error = True
                    user = None
        return user, error, messages

    def send_confirmation_email(self):
        email = EmailMessage()
        email['Subject'] = 'User registration confirmation for Nitecap access'
        email['From'] = 'donotreply@nitecap.itmat.upenn.edu'
        email['To'] = self.email
        email.set_content(f'Please click on this link to confirm your registration. http://127.0.0.1:5000/confirm_user/{self.id}')
        s = smtplib.SMTP(host='127.0.0.1', port=25)
        #s.starttls()
        #s.login('you@gmail.com', 'password')
        s.send_message(email)
        s.quit()

    @classmethod
    def confirm_user(cls, _id):
        user = User.find_by_id(_id)
        if user:
            user.activated = True
            user.save_to_db()
        return user

    @classmethod
    def find_by_email(cls, email):
        return cls.query.filter_by(email=email).first()

    @classmethod
    def find_by_username(cls, username):
        return cls.query.filter_by(username=username).first()

    @classmethod
    def find_by_id(cls, _id):
        return cls.query.filter_by(id=_id).first()

    def save_to_db(self):
        db.session.add(self)
        db.session.commit()





