import datetime
import smtplib

from flask import url_for, request

from models.confirmations.confirmation import Confirmation
from security import check_encrypted_password, encrypt_password
from db import db
import os
from email.message import EmailMessage


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False, unique=True)
    email = db.Column(db.String(150), nullable=False, unique=True)
    password = db.Column(db.String(100), nullable=False)
    last_access = db.Column(db.DateTime)

    confirmation = db.relationship("Confirmation", lazy="dynamic", cascade="all, delete-orphan")

    @property
    def most_recent_confirmation(self):
        return self.confirmation.order_by(db.desc(Confirmation.expire_at)).first()

    def __init__(self, username, email, password, last_access=None):
        self.username = username
        self.email = email
        self.password = password
        self.last_access = last_access if last_access else datetime.datetime.now()

    def __repr__(self):
        return f"<User id:{self.id}, username: {self.username}, email: {self.email} last acess: {self.last_access}>"

    @staticmethod
    def register_user(username, email, password):
        messages = []
        user = None
        status = ''
        if not email:
            messages.append("You must supply an email address.")
            status = 'error'
        if not password:
            messages.append("You must supply a password.")
            status = 'error'
        elif email and password:
            user, status, message = User.check_existence(email, password)
            if message:
                messages.append(message)
        if not user:
            if not username:
                username = email
            user = User.find_by_username(username)
            if user:
                messages.append("The username you provided is already registered.")
                status = 'error'
                user = None
            else:
                password = encrypt_password(password)
                user = User(username, email, password)
                user.save_to_db()
                confirmation = Confirmation(user.id)
                confirmation.save_to_db()
                status, messages = user.send_confirmation_email()
        return user, status, messages

    @staticmethod
    def login_user(username, password):
        messages = []
        status = ''
        user = User.find_by_username(username)
        if not user:
            user = User.find_by_email(username)
            if not user:
                messages.append("No such user currently exists in the site.  Please register.")
                status = 'error'
                user = None
        if user:
            if not check_encrypted_password(password, user.password):
                messages.append("Invalid credentials.  Try again.")
                status = 'error'
                user = None
            else:
                confirmation = user.most_recent_confirmation

                if confirmation and confirmation.confirmed:
                    user.last_access = datetime.datetime.now()
                    user.save_to_db()
                else:
                    messages.append("You need to click on the confirmation link we emailed you before you can login.  "
                                    "Please check your spam folder.")
                    status = 'unconfirmed'
        return user, status, messages

    def send_confirmation_email(self):
        status = ''
        message = []
        email = EmailMessage()
        email['Subject'] = 'User registration confirmation for Nitecap access'
        email['From'] = os.environ.get('EMAIL_SENDER')
        email['To'] = self.email
        link = request.url_root[:-1] + url_for("confirmations.confirm_user", confirmation_id=self.most_recent_confirmation.id)
        email.set_content(f'Please click on this link to confirm your registration. {link}')

        # If sendmail fails for any reason, we drop the user from the db so that the user may re-register.
        try:
            s = smtplib.SMTP(host='127.0.0.1', port=25)
            #s.starttls()
            #s.login('you@gmail.com', 'password')
            s.send_message(email)
            s.quit()
        except:
            self.delete_from_db()
            status = 'error'
            message = "A confirmation email could not be sent at this time.  " \
                      "Please attempt a registration later or notify us of the problem."
        return status, message


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

    def delete_from_db(self):
        db.session.delete(self)
        db.session.commit()

    @staticmethod
    def check_existence(email, password):
        status = None
        message = None
        user = User.find_by_email(email)
        if user:
            if check_encrypted_password(password, user.password):
                if not user.most_recent_confirmation.confirmed:
                    status = 'unconfirmed'
                    message = "You are already registered but have not activated " \
                          "your account by clicking on the email confirmation link sent to you."
                else:
                    status = 'confirmed'
                    message = "You are already registered and your account is activated.  Just log in."
            else:
                status = 'error'
                message = 'The e-mail you provided is already registered.'
                user = None
        return user, status, message





