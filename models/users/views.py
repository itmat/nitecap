from flask import Blueprint, request, session, url_for, redirect, render_template, flash

from models.spreadsheets.spreadsheet import Spreadsheet
from models.users.user import User
from models.users.decorators import requires_login

user_blueprint = Blueprint('users', __name__)

@user_blueprint.route('/register', methods=['GET','POST'])
def register_user():
    """
    Handles user registration.  The GET method requests the form.  The POST method attempts to process the user's
    input.  A successful registration takes the user to a page acknowledging the delivery of a confirmation email.
    A rendundant registration forwards the user to a login page if the user account is activated and to a resend
    confirmation page otherwise.  A unsuccessful registration returns the users to the registration form with the
    errors noted.
    """

    if request.method == 'POST':
        errors = []
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        if not email:
            errors.append("Email is required.")
        if not password:
            errors.append("Password is required.")

        user, errors, status = User.register_user(username, email, password)

        # Either user filled out the form incorrectly (possibly duplicate email or username or a required entry left
        # empty) or no confirmation email could be sent.
        if errors:
            return render_template('users/registration_form.html',
                                   username=username, email=email,
                                   errors=errors)

        # User already registered but not activated.  May have ignored or not received confirmation email.
        # Invited user to check email or resend the confirmation email.
        if status == 'unconfirmed':
            flash("You are already registered but have not activated "
                  "your account by clicking on the email confirmation link sent to you.")
            return render_template('confirmations/resend_confirmation_form.html',
                                   confirmation_id=user.most_recent_confirmation.id,
                                   email=user.email)

        # User already registered and activated.  Send user to login page.
        if status == 'confirmed':
            flash("You are already registered and your account is activated.  Just log in.")
            return render_template('users/login_form.html', username = user.username)

        # User successfully registered and email sent.
        flash("A confirmation email has been sent.")
        return redirect(url_for('spreadsheets.load_spreadsheet'))

    else:

        # User requests registration form.
        return render_template('users/registration_form.html')

@user_blueprint.route('/login', methods=['GET','POST'])
def login_user():
    """
    Handles user login.  The GET method requests the form.  The POST method attempts to process the user's input.
    A successful login takes the user back to the spreadsheet loading form page.  A login that is unsuccessful owing
    to an empty field or invalid credentials is returned to the login form with errors noted.  A login that is
    unsuccessful because the user's account is not yet activated, takes the user to the resend confirmation page
    where the user may resend a confirmation email.
    """

    next = request.args.get('next')
    print(next)
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = None
        errors = []
        messages = []

        # User must populate the username and password fields.
        if not username:
            errors.append("Username is required.  You may use your email address as your username.")
        if not password:
            errors.append("Password is required.")

        # The user is either not activated or has submitted invalid creds.
        if username and password:
            user, errors, messages = User.login_user(username, password)

        # User did not log in correctly - empty field or invalid credentials.  Return user to login form and note
        # errors.
        if errors:
            return render_template('users/login_form.html', username = username, errors = errors)

        # User's account is not yet activated - possibly user ignored confirmation email or never received it.
        # Invite user to resend confirmation email.
        if messages:
            [flash(message) for message in messages]
            return render_template('confirmations/resend_confirmation_form.html',
                                    email = user.email,
                                    confirmation_id = user.most_recent_confirmation.id)

        # Log in user and redirect to the spreadsheet loading form.
        if user:
            session['email'] = user.email
            if 'spreadsheet_id' in session and session['spreadsheet_id']:
                spreadsheet_id = session['spreadsheet_id']
                spreadsheet = Spreadsheet.find_by_id(spreadsheet_id)
                if spreadsheet.user.is_annoymous_user():
                    spreadsheet.update_user(user.id)

        # If the user logged in from a different page on this website, return to that page.
        if next and next != '/users/logout':
            return redirect(next)

        return redirect(url_for("spreadsheets.load_spreadsheet"))

    # User requests login form.
    return render_template('users/login_form.html', next=next)

@user_blueprint.route('/logout', methods=['GET'])
def logout_user():
    """
    Removes the user's email from the session, thereby logging the user off.
    :return: Returning user to spreadsheet upload form in lieu of a home page
    """

    session['email'] = None
    session['spreadsheet_id'] = None
    return render_template('spreadsheets/spreadsheet_upload_form.html')

@user_blueprint.route('/reset_password', methods=['GET','POST'])
def request_password_reset():
    """
    Handles request for a password reset.  The link to this URL is found on the login form under the
    password input.  The GET requests the request form.  The POST will validate the email provided an
    attempt to issue a password reset to that email address.  A successful POST will return the user
    to the login page to await the password reset email.  An unsuccessful POST will take the user to
    the registration form if the email provided is not associated with any current account.
    """

    errors = []

    # Should be no need for a password reset if the user is already logged in.
    if 'email' in session and session['email']:
        flash("You are already logged in.  You must be logged out to request a password reset")

    # User submits password reset request form
    if request.method == 'POST':

        # The email input is required
        email = request.form['email']
        if not email:
            errors.append("You must provide your email.")
            return render_template('users/request_reset_form.html', errors=errors)

        # The email provided must be associated with an existing account.
        user = User.find_by_email(email)
        if not user:
            errors.append("There is no account with that email.  Please register.")
            return render_template('users/registration_form.html', email=email, errors=errors)

        # If email delivery was not successful take the user to the spreadsheet load page with
        # an error
        errors = user.send_reset_email()
        if errors:
            return render_template('spreadsheets/spreadsheet_upload_form.html', errors=errors)

        # Notify user the an email has been sent.
        flash("An email has been sent with instructions for reseting your password")
        return redirect(url_for('users.login_user'))

    # User requests password reset request form
    return render_template('users/request_reset_form.html')

@user_blueprint.route('/reset_password/<string:token>', methods=['GET','POST'])
def reset_password(token):
    """
    Handles the password reset itself.  The link to this URL is provided in the password reset request
    email send to the user.  The GET requests the password reset form.  The user must be logged out to
    use this facility.  A successful POST will reset the user's password to the one provided in the
    form and redirect the user to the login page.  An unsuccessful POST will return the user to the
    password reset form and note the errors made so the user may correct them.
    :param token: short during token used to identify user - contains user id encrypted
    """

    errors = []

    # Should be no need for a password reset if the user is already logged in.
    if 'email' in session and session['email']:
        flash("You are already logged in.  You must be logged out to reset your password")
        return render_template('users/request_reset_form.html')

    # The token must be valid and not yet expired.
    user = User.verify_reset_token(token)
    if not user:
        errors.append("Your reset request is either invalid or expired.  Please try again.")
        return render_template('users/request_reset_form.html', errors=errors)

    # User submits password reset form
    if request.method == 'POST':

        # Both password input fields must be populated.
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        if not password or not confirm_password:
            errors.append("You must provide the password and retype it to confirm.")
            return render_template('users/reset_password_form.html', errors=errors)

        # Both password input fields must match
        if password != confirm_password:
            errors.append("The password and confirm password entries do not match.")
            return render_template('users/reset_password_form.html', errors=errors)

        # Reset the user's password
        user.reset_password(password)
        flash("Your password has been reset.")
        return redirect(url_for('users.login_user'))

    # User requests password reset form.
    return render_template('users/reset_password_form.html', token=token)

@user_blueprint.route('/update_profile', methods=['GET','POST'])
@requires_login
def update_profile():
    errors = []

    user = User.find_by_email(session['email'])

    if request.method == 'POST':

        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        user.update_user_profile(username, email, password)
        if email:
            session['email'] = email

        flash("Your user profile has been updated.")
        return render_template("spreadsheets/spreadsheet_upload_form.html")

    return render_template('users/profile_form.html', username=user.username, email=user.email)





