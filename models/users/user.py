import datetime
import smtplib

from flask import url_for, request

from models.confirmations.confirmation import Confirmation
from security import check_encrypted_password, encrypt_password
from db import db
import os
from email.message import EmailMessage
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False, unique=True)
    email = db.Column(db.String(150), nullable=False, unique=True)
    password = db.Column(db.String(100), nullable=False)
    last_access = db.Column(db.DateTime)

    confirmation = db.relationship("Confirmation", lazy="dynamic", cascade="all, delete-orphan")
    spreadsheet = db.relationship("Spreadsheet", lazy='dynamic', cascade="all, delete-orphan")

    @property
    def most_recent_confirmation(self):
        return self.confirmation.order_by(db.desc(Confirmation.expire_at)).first()

    @property
    def spreadsheets(self):
        return self.spreadsheet

    def __init__(self, username, email, password, last_access=None):
        self.username = username
        self.email = email
        self.password = password
        self.last_access = last_access if last_access else datetime.datetime.now()

    def __repr__(self):
        return f"<User id:{self.id}, username: {self.username}, email: {self.email} last acess: {self.last_access}>"

    @staticmethod
    def register_user(username, email, password):
        user, errors, status = User.check_existence(email, password)
        if not user:
            if not username:
                username = email
            user = User.find_by_username(username)
            if user:
                errors.append("The username you provided is already registered.")
                user = None
            else:
                password = encrypt_password(password)
                user = User(username, email, password)
                user.save_to_db()
                confirmation = Confirmation(user.id)
                confirmation.save_to_db()
                email_errors = user.send_confirmation_email()
                if email_errors:
                    errors.extend(email_errors)
        return user, errors, status

    @staticmethod
    def login_user(username, password):
        messages = []
        errors = []
        user = User.find_by_username(username)
        if not user:
            user = User.find_by_email(username)
            if not user:
                errors.append("No such user currently exists in the site.  Please register.")
                user = None
        if user:
            if not check_encrypted_password(password, user.password):
                errors.append("Invalid credentials.  Try again.")
                user = None
            else:
                confirmation = user.most_recent_confirmation

                if confirmation and confirmation.confirmed:
                    user.last_access = datetime.datetime.now()
                    user.save_to_db()
                else:
                    messages.append("You need to click on the confirmation link we emailed you before you can login.  "
                                    "Please check your spam folder.")
        return user, errors, messages

    def update_user_profile(self, username, email, password):
        if username:
            self.username = username
        if email:
            self.email = email
        if password:
            self.password = encrypt_password(password)
        self.save_to_db()

    def send_confirmation_email(self):
        errors = []
        subject = 'User registration confirmation for Nitecap access'
        sender = os.environ.get('EMAIL_SENDER')
        link = request.url_root[:-1] + url_for("confirmations.confirm_user", confirmation_id=self.most_recent_confirmation.id)
        content = f'Please click on this link to confirm your registration. {link}'
        error = self.send_email(subject, sender, content)
        if error:
            errors.append("A confirmation email could not be sent at this time.  "
                      "Please attempt a registration later or notify us of the problem.")
        return errors

    def send_reset_email(self):
        token = self.get_reset_token()
        errors = []
        subject = 'User password reset for Nitecap access'
        sender = os.environ.get('EMAIL_SENDER')
        link = request.url_root[:-1] + url_for("users.reset_password", token=token)
        content = f'Please click on this link to reset your password. {link}'
        error = self.send_email(subject, sender, content)
        if error:
            errors.append("A password reset email could not be sent at this time.  "
                          "Please request a password reset later or notify us of the problem.")
        return errors

    def send_email(self, subject, sender, content):
        error = False
        email = EmailMessage()
        email['Subject'] = subject
        email['From'] = sender
        email['To'] = self.email
        email.set_content(content)

        # If sendmail fails for any reason, we drop the user from the db so that the user may re-register.
        try:
            s = smtplib.SMTP(host='127.0.0.1', port=25)
            # s.starttls()
            # s.login('you@gmail.com', 'password')
            s.send_message(email)
            s.quit()
        except:
            self.delete_from_db()
            error = True
        return error

    def get_reset_token(self, expires_sec = 1800):
        s = Serializer(os.environ['SECRET_KEY'], expires_sec)
        return s.dumps({'user_id': self.id}).decode('utf-8')

    @staticmethod
    def verify_reset_token(token):
        s = Serializer(os.environ['SECRET_KEY'])
        try:
            user_id = s.loads(token)['user_id']
        except:
            return None
        return User.find_by_id(user_id)

    def reset_password(self, password):
        self.password = encrypt_password(password)
        self.save_to_db()

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

    def find_user_spreadsheet_by_id(self, spreadsheet_id):
        return self.spreadsheet.filter_by(id=spreadsheet_id).first()

    def save_to_db(self):
        db.session.add(self)
        db.session.commit()

    def delete_from_db(self):
        db.session.delete(self)
        db.session.commit()

    @staticmethod
    def check_existence(email, password):
        status = None
        errors = []
        user = User.find_by_email(email)
        if user:
            if check_encrypted_password(password, user.password):
                if not user.most_recent_confirmation.confirmed:
                    status = 'unconfirmed'
                else:
                    status = 'confirmed'
            else:
                errors.append('The e-mail you provided is already registered.')
                user = None
        return user, errors, status

    @classmethod
    def create_annonymous_user(cls):
        password = encrypt_password(os.environ['ANNONYMOUS_PWD'])
        user = cls('annonymous', os.environ['ANNONYMOUS_EMAIL'], password)
        user.save_to_db()
        return user


    def is_annoymous_user(self):
        return self.username == 'annonymous'



