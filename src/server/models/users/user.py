import boto3
import datetime
import pathlib
import random
import requests
import shutil
import string
from string import Template
from flask import url_for, request

from security import check_encrypted_password, encrypt_password
from db import db
import os
from email.message import EmailMessage
from itsdangerous import TimedJSONWebSignatureSerializer as TimedSerializer
from flask import current_app

CONFIRMATION_EXPIRATION_DELTA = 6 * 60 * 60
PASSWORD_RESET_EXPIRATION_DELTA = 30 * 60
PASSWORD_CHAR_SET = string.ascii_letters + string.digits + string.punctuation
PASSWORD_LENGTH = 12

# Due to spammers entering stuff in our users we blacklist some contents in usernames
BLACKLISTED_USERNAME_CONTENTS = ["https:", "$"]
BLACKLISTED_EMAIL_CONTENTS = ["https:", "$"]

ses = boto3.client("ses")
dynamodb = boto3.resource("dynamodb")
suppression_list = dynamodb.Table(os.environ["EMAIL_SUPPRESSION_LIST_NAME"])
EMAIL_CONFIGURATION_SET_NAME = os.environ["EMAIL_CONFIGURATION_SET_NAME"]

class User(db.Model):
    __tablename__ = "users"
    __table_args__ = {
        "sqlite_autoincrement": True,
    }
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False, unique=True)
    email = db.Column(db.String(150), nullable=False, unique=True)
    password = db.Column(db.String(100), nullable=False)
    last_access = db.Column(db.DateTime)
    visitor = db.Column(db.Boolean, default=True)
    activated=db.Column(db.Boolean, nullable=False, default=False)

    USER_DIRECTORY_NAME_TEMPLATE = Template('user_$user_id')

    spreadsheet = db.relationship("Spreadsheet", lazy='dynamic', cascade="all, delete-orphan", back_populates="user")

    @property
    def spreadsheets(self):
        return self.spreadsheet

    def __init__(self, username, email, password, visitor=True, last_access=None):
        """
        This method initializes a new user.  SQLAlchemy does not run this method when recovering a user from the
        database (it uses __new__ only).
        :param username: The user's username.  If the user doesn't supply one, the user's email becomes the user's
        username as well.
        :param email: The user's email.  Also the address where registration confirmation and password reset emails
        are sent.
        :param password:  The user's password.  Saved in the database in pbkdf2_sha256 encrypted hash.
        :param visitor: Indicates a visitor's account.
        :param last_access: The timepoint indicating the user's last access.  Not sure this is useful here since a
        user recovered from the database does not pass this way.
        """
        self.username = username
        self.email = email
        self.password = password
        self.visitor = visitor
        self.last_access = last_access if last_access else datetime.datetime.utcnow()

    def __repr__(self):
        """
        A representation of the user's data
        :return: A string representation of the user
        """
        return f"<User id:{self.id}, username: {self.username}, email: {self.email} last acess: {self.last_access}>"

    @staticmethod
    def register_user(username, email, password):
        """
        Attempts to register a user given an email and new credentials
        :param username: username of user which may be None
        :param email: required email address for the user
        :param password: reguired password (in plain text here - assuming https connection) for the user
        :return: The user object or none, any errors, and the status (None, confirmed, unconfirmed).  The user object
        is only provided if the registering user is found to already exist or if the registering user is successfully
        registered.
        """
        user, errors, status = User.check_existence(email, password)

        # If the user exists already, there is no need to register, so just return the user object.
        if not user:

            # If the username is not provided, substitute the email address (the view validates that an email
            # address was provided.
            if not username:
                username = email

            # If the username is already in use by another user, prompt this user to choose a different username
            user = User.find_by_username(username)
            if user:
                errors.append(f"The username, {username}, you provided is already registered.")
                user = None

            # Check if the username or email contain any blacklisted sub-strings
            # and reject if they do (a weak spam-protection)
            username_bad = any([(marker in username) for marker in BLACKLISTED_USERNAME_CONTENTS ])
            email_bad = any([(marker in email) for marker in BLACKLISTED_EMAIL_CONTENTS ])
            if username_bad or email_bad:
                errors.append(f"Invalid input.")

            # Otherwise encrpyt the password, instantiate the user and save the user to the database.  Then create
            # confirmation email and deliver it.
            if len(errors) == 0:
                password = encrypt_password(password)
                # Flag this user as NOT a visitor
                user = User(username, email, password, False)
                user.save_to_db()
                email_errors = user.send_confirmation_email()
                if email_errors:
                    errors.extend(email_errors)
        return user, errors, status

    @staticmethod
    def login_user(username, password):
        """
        Logs in the user given his/her credentials (username, password)
        :param username: Either the username the user registered or the user's email address.
        :param password: Password in clear text (assuming https connection)
        :return: The user object, any errors, any messages.  An error suggests a possible bad
        input whereas a message suggests that the user needs to be informed of a missing step. No user
        object is returned if credentials are found to be invalid.
        """
        messages = []
        errors = []

        # First look for the user by username and if not successful, look for the user by email.  This is
        # probably redundant since the username is the email unless the user provided a username at registration.
        # So either way, the user should be found by username.
        user = User.find_by_username(username)
        if not user:
            user = User.find_by_email(username)
            if not user:
                errors.append("No such user currently exists in the site.  Please register.")
                user = None

        # Insure that the offered password matches the one in the database, once encrypted.  If the password is
        # correct, verify that the user has confirmed his/her registration and if so, update the user's last access.
        # Otherwise inform the user of invalid credentials or lack of confirmation.
        if user:
            # visitor accounts cannot 'log in'
            if user.visitor:
                errors.append("Not a valid user.  Please register.")
                current_app.logger.warn(f"Attempt made to log in with visitor account {user.username}")
                return user, errors, messages

            if not check_encrypted_password(password, user.password):
                errors.append("Invalid credentials.  Try again.")
                user = None
            else:
                if user.activated:
                    user.last_access = datetime.datetime.utcnow()
                    user.save_to_db()
                else:
                    messages.append("You need to click on the confirmation link we emailed you before you can login.  "
                                    "Please check your spam folder.")
        return user, errors, messages

    def update_user_profile(self, username, email, password):
        """
        Updates the user data in the database.  Only fields that have data get changed.
        :param username: user's new username or None
        :param email: user's new email address or None
        :param password: user's new password or None
        """
        if username:
            self.username = username
        if email:
            self.email = email
        if password:
            self.password = encrypt_password(password)
        self.save_to_db()

    def send_confirmation_email(self):
        """
        Sends a registration confirmation email to the user's provided email address.  The email contains a link to a
        confirmation page along with a short-lived encrypted token to protect against hacking.  When the user clicks
        the link, his/her registration will be confirmed as long as it is done within the elapsed time given in minutes
        by the CONFIRMATION_EXPIRATION_DELTA of this class.
        :return: Any errors that occur in the process of delivering the email.
        """

        token = self.get_confirmation_token()
        errors = []
        subject = 'User registration confirmation for Nitecap access'
        sender = os.environ.get('EMAIL_SENDER')
        link = request.url_root[:-1] + url_for("users.confirm_user", token=token)
        content = f'Please click on this link to confirm your registration. {link}'
        error = self.send_email(subject, sender, content)
        if error:
            errors.append("A confirmation email could not be sent at this time.  "
                          "Please attempt a registration later or notify us of the problem.")
        return errors

    def send_reset_email(self):
        """
        Send a password reset email to the user's provided email address.  The email contains a link to a
        password reset page along with a short-lived token that identified the user to the server.  When the user
        clicks the link, s/he will be allowed to reset his/her password.
        :return:  Any errors that occur in the process of delivering the email.
        """
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

    def email_is_in_supression_list(self) -> bool:
        return "Item" in suppression_list.get_item(Key={"email": self.email})

    def email_is_in_spam_list(self) -> bool:
        response = requests.request(
            "GET", f"https://api.stopforumspam.org/api?email[]={self.email}"
        )

        return "<appears>yes</appears>" in response.text

    def send_email(self, subject, sender, content):
        """
        Sends an email to the user.
        :param subject: The email subject line
        :param sender: The address of the sender (input via an environmental variable)
        :param content: The email body.
        :return: Any problem with delivery is noted with an error flag.
        """
        error = False

        if self.email_is_in_supression_list() or self.email_is_in_spam_list():
            current_app.logger.info(f"Email in suppression or spam list: {self.email}")
            error = True
        else:
            try:
                ses.send_email(
                    Source=sender,
                    Destination={
                        "ToAddresses": [self.email],
                    },
                    Message={
                        "Subject": {"Data": subject},
                        "Body": {"Text": {"Data": content}},
                    },
                    ConfigurationSetName=EMAIL_CONFIGURATION_SET_NAME,
                )
                current_app.logger.info(f"Email sent: {self.email}")
            except Exception as exception:
                current_app.logger.error(f"Email delivery failed: {exception}")
                error = True
            
        return error

    def get_confirmation_token(self, expires_sec=CONFIRMATION_EXPIRATION_DELTA):
        """
        User the SECRET_KEY to fashion a token which contains the user's id.  The token is emailed to the user when a
        prospective new user registers for an account.  The user is recognized by the token's contents and allowed to
        log in.
        :param expires_sec: The number of seconds until the token expires
        :return: a short-lived, encrypted token
        """
        s = TimedSerializer(os.environ['SECRET_KEY'], expires_sec)
        return s.dumps({'user_id': self.id}).decode('utf-8')

    def get_reset_token(self, expires_sec=PASSWORD_RESET_EXPIRATION_DELTA):
        """
        Uses the SECRET_KEY to fashion a token which contains the user's id.  The token is emailed to the user when a
        password reset request is made.  The user is recognized by the token's contents and allowed then to update his/
        her password.
        :param expires_sec: The number of seconds until the token expires
        :return: a short-lived, encrypted token
        """
        s = TimedSerializer(os.environ['SECRET_KEY'], expires_sec)
        return s.dumps({'user_id': self.id}).decode('utf-8')

    @staticmethod
    def verify_user_token(token):
        """
        Validates the freshness and content of a token.  The user identified by the user id in the token must be
        findable.
        :param token: token used for user confirmation or password reset.
        :return: The user identified in the token or None
        """
        s = TimedSerializer(os.environ['SECRET_KEY'])
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
        """
        Confirms a user by setting the activated flag for that user record to true in the database.  This allows the
        user to log in with their credentials going forward.
        :param _id: user id
        :return: The user object now with the activated flag set.
        """
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

    @classmethod
    def find_all_users(cls):
        return cls.query.all()

    @classmethod
    def find_visitors(cls):
        """
        Finds all visitor accounts.
        :return: list of visitor accounts
        """
        return cls.query.filter_by(visitor=True)

    @staticmethod
    def spreadsheet_counts():
        """
        Finds the number of spreadsheets owned by each user
        :return: a map of user_id to spreadsheet count.  The absense of a user_id indicates the the user owns no
        spreadsheets
        """
        from sqlalchemy import func
        from models.spreadsheets.spreadsheet import Spreadsheet
        results = db.session.query(User.id, func.count(Spreadsheet.id)).join(User.spreadsheet).group_by(User.id).all()
        user_counts_map = {user_id : spreadsheet_count for user_id, spreadsheet_count in results}
        return user_counts_map

    @staticmethod
    def check_existence(email, password):
        """
        Determine whether this set of credentials is already in the database.  If the email address matches but the
        password does not, notify the user that the email provided is already registered.  If the email and password
        match an existing database entry, check to see whether the registration has been confirmed.
        :param email: the email address offered by the registering user
        :param password: the password offered by the registering user
        :return: The user object, any errors and if the credentials exist in the database, whether or not the
        registration is confirmed.
        """
        status = None
        errors = []
        user = User.find_by_email(email)
        if user:
            if check_encrypted_password(password, user.password):
                if not user.activated:
                    status = 'unconfirmed'
                else:
                    status = 'confirmed'
            else:
                errors.append('The e-mail you provided is already registered.')
                user = None
        return user, errors, status


    @classmethod
    def create_visitor(cls):
        """
        Creates a visitor account with a unique data using the password to start with.  Then revising the
        database entry for username and email based on the user id returned by the database.  The password
        is temporariliy used as the username and email address only to avoid a violation of the uniqueness
        constraint.
        :return: visiting user
        """
        password = encrypt_password(User.generate_password())
        user = cls(password, f'{password}@nitecap.org', password)
        user.save_to_db()
        user.username = f'user_{user.id}'
        user.email = f'{user.username}@nitecap.org'
        user.save_to_db()
        return user

    def is_visitor(self):
        """
        Returns account status - whether or not the account belongs to a visitor.
        :return: true if visitor account and false otherwise.
        """
        return self.visitor

    def delete(self):
        """
        Removes this user from the database and discards the directory associated with this user, if one exists.  A
        user may have an account but no directory, in the case where s/he has never uploaded any data or copied a
        share.  We also remove the user directory before removing the user since sqlite3 auto-increments to obtain ids
        and could potentially re-use this one if it is the last id generated.
        """
        if os.path.exists(self.get_user_directory_path()):
            shutil.rmtree(self.get_user_directory_path())
        self.delete_from_db()

    @staticmethod
    def generate_password():
        """
        Generates a password for use with visitor accounts.
        :return: random string of PASSWORD_LENGTH characters
        """
        return ''.join(random.choice(PASSWORD_CHAR_SET) for _ in range(PASSWORD_LENGTH))

    def get_user_directory_name(self):
        """
        Return the name of the user directory (not the absolute path)
        """
        return User.USER_DIRECTORY_NAME_TEMPLATE.substitute(user_id=self.id)

    def get_user_directory_path(self):
        """
        Helper method to identify the path to the user's directory where the user's spreadsheet data is maintained.
        This directory path is constructed by convention - not saved to the db.
        :return: path to the user's directory.
        """
        return str(pathlib.Path(os.environ.get('UPLOAD_FOLDER'))/self.get_user_directory_name())

    def reassign_visitor_spreadsheets(self, visitor):
        """
        Now that a visitor has logged in, we need to move any work the visitor did over to the login account.  This
        involves moving any spreadsheet data the visitor created over to the logged in account and updating that
        spreadsheet metadata with the new user id and paths.  Additionally, now that the visitor account is abandoned,
        we can throw away the related user db record and the directory associated with the visitor.
        :param visitor: the visiting user account
        """
        # Import here to avoid circular imports
        from computation.api import store_spreadsheet_to_s3

        user_directory_name = self.get_user_directory_name()
        user_directory_path = self.get_user_directory_path()

        # Iterate over all spreadsheets belonging to to visitor
        for spreadsheet in visitor.spreadsheets:

            # Create spreadsheet data directory under user directory and move visitor spreadsheet data there.
            visitor_spreadsheet_directory_name = spreadsheet.get_spreadsheet_data_directory_name()
            new_spreadsheet_data_folder = os.path.join(user_directory_path, visitor_spreadsheet_directory_name)
            shutil.move(spreadsheet.get_spreadsheet_data_folder(), new_spreadsheet_data_folder)

            # Update spreadsheet owner, repoint all spreadsheet paths to owner's directory and save
            spreadsheet.user_id = self.id
            spreadsheet.spreadsheet_data_path = os.path.join(user_directory_name, visitor_spreadsheet_directory_name)
            spreadsheet.save_to_db()

            # Needs to be re-uploaded to the new user's 'folder'
            if spreadsheet.has_metadata():
                spreadsheet.init_on_load()
                store_spreadsheet_to_s3(spreadsheet)

        # Finally discard the visitor directory path and remove the visitor from the database
        visitor.delete()
