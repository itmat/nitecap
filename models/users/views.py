import json

from flask import Blueprint, request, session, url_for, redirect, render_template, flash, jsonify

from models.users.user import User
from models.users.decorators import requires_login, requires_admin
from flask import current_app

user_blueprint = Blueprint('users', __name__)

ACCOUNT_NOT_FOUND_MESSAGE = "No such account was found.  Please register."
PROFILE_UPDATED_MESSAGE = "Your user profile has been updated."
MISSING_USER_ID_ERROR = "No user id was provided."
PASSWORD_RESET_MESSAGE = "Your password has been reset"
PASSWORD_RESET_SENT_MESSAGE = "An email has been sent with instructions for reseting your password"
PASSWORD_RESET_TOKEN_EXPIRED = "Your reset request is either invalid or expired.  Please try again."
ALREADY_LOGGED_IN_MESSAGE = "You are already logged in.  Log out first to resent password."
ALREADY_ACTIVATED_MESSAGE = "You are already activated.  If you are still unable to log in, please communicate with us."
CONFIRMATION_SENT_MESSAGE = "Your confirmation email has been sent.  Click on the link it contains to activate your" \
                            " account."
CONFIRMATION_TOKEN_EXPIRED = "Your confirmation request is either invalid or expired.  Please reconfirm by attempting" \
                             "to log in.  You will be re-directed to the resend confirmation page."


@user_blueprint.route('/register', methods=['GET', 'POST'])
def register_user():
    """
    Standard endpoint - handles user registration.  The GET method requests the form.  The POST method attempts to process the user's
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
            flash("You are already registered but have not activated.  Activate "
                  "your account by clicking on the email confirmation link sent to you.")
            return redirect(url_for('.resend_confirmation'))

        # User already registered and activated.  Send user to login page.
        if status == 'confirmed':
            flash(ALREADY_ACTIVATED_MESSAGE)
            return redirect(url_for('.login_user'))

        # User successfully registered and email sent.
        current_app.logger.info(f"user {username} - {email} just registered.")
        flash(CONFIRMATION_SENT_MESSAGE)
        return redirect(url_for('spreadsheets.load_spreadsheet'))

    else:

        # User requests registration form.
        return render_template('users/registration_form.html')


@user_blueprint.route('/login', methods=['GET', 'POST'])
def login_user():
    """
    Handles user login.  The GET method requests the form.  The POST method attempts to process the user's input.
    A successful login takes the user back to the spreadsheet loading form page.  A login that is unsuccessful owing
    to an empty field or invalid credentials is returned to the login form with errors noted.  A login that is
    unsuccessful because the user's account is not yet activated, takes the user to the resend confirmation page
    where the user may resend a confirmation email.
    """

    next_url = request.args.get('next')
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

        # The user is either not activated or has submitted invalid credentials.
        if username and password:
            user, errors, messages = User.login_user(username, password)

        # User did not log in correctly - empty field or invalid credentials.  Return user to login form and note
        # errors.
        if errors:
            return render_template('users/login_form.html', username=username, errors=errors)

        # User's account is not yet activated - possibly user ignored confirmation email or never received it.
        # Invite user to resend confirmation email.
        if messages:
            [flash(message) for message in messages]
            return redirect(url_for('.resend_confirmation', email=user.email))

        # Log in user and redirect to the user spreadsheets form.
        if user:

            # A prior user session suggests that the newly logged in user was a originally visitor and that he/she
            # created spreadsheets prior to logging in and we should re-point them to his/her logged in account.
            if 'email' in session:
                prior_user = User.find_by_email(session['email'])
                if prior_user and prior_user.is_visitor():
                    for spreadsheet in prior_user.spreadsheets:
                        spreadsheet.update_user(user.id)

            session.permanent=True
            session['email'] = user.email
            session['visitor'] = False

        # If the user logged in from a different page on this website, return to that page with the exception of
        # the logout route or the home page.
        if next_url and next_url != '/users/logout' and next_url != '/':
            return redirect(next_url)

        return redirect(url_for("spreadsheets.display_spreadsheets"))

    # User requests login form.
    return render_template('users/login_form.html', next=next_url)


@user_blueprint.route('/logout', methods=['GET'])
def logout_user():
    """
    Removes the user's email from the session, thereby logging the user off.
    :return: Returning user to spreadsheet upload form in lieu of a home page
    """

    session.clear()
    return redirect(url_for('spreadsheets.upload_file'))


@user_blueprint.route('/reset_password', methods=['GET', 'POST'])
def request_password_reset():
    """
    Standard endpoint - handles request for a password reset.  The link to this URL is found on the login form under
    the password input.  The GET requests the request form.  The POST will validate the email provided an attempt to
    issue a password reset to that email address.  A successful POST will return the user to the login page to await
    the password reset email.  An unsuccessful POST will take the user to the registration form if the email provided
    is not associated with any current account.
    """

    # Should be no need for a password reset if the user is already logged in and is not a visitor.
    if 'email' in session and session['email']:
        user = User.find_by_email(session['email'])
        if user and not user.is_visitor():
            flash(ALREADY_LOGGED_IN_MESSAGE)
            return redirect(url_for('spreadsheets.display_spreadsheets'))

    # User submits password reset request form
    if request.method == 'POST':

        # The email input is required
        email = request.form['email']
        if not email:
            return render_template('users/request_reset_form.html', errors="You must provide your email.")

        # The email provided must be associated with an existing account.
        user = User.find_by_email(email)
        if not user:
            flash(ACCOUNT_NOT_FOUND_MESSAGE)
            return redirect(url_for('.register_user'))

        # If email delivery was not successful take the user to the spreadsheet load page with
        # an error
        errors = user.send_reset_email()
        if errors:
            return render_template('spreadsheets/upload_file.html', errors=errors)

        # Notify user the an email has been sent.
        flash(PASSWORD_RESET_SENT_MESSAGE)
        return redirect(url_for('.login_user'))

    # User requests password reset request form
    return render_template('users/request_reset_form.html')


@user_blueprint.route('/reset_password/<string:token>', methods=['GET', 'POST'])
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

    # Should be no need for a password reset if the user is already logged in and not a visitor.
    if 'email' in session and session['email']:
        user = User.find_by_email(session['email'])
        if user and not user.is_visitor():
            flash(ALREADY_LOGGED_IN_MESSAGE)
            return redirect(url_for('spreadsheets.display_spreadsheets'))

    # The token must be valid and not yet expired.
    user = User.verify_user_token(token)
    if not user:
        flash(PASSWORD_RESET_TOKEN_EXPIRED)
        return redirect(url_for('.request_password_reset'))

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
        flash(PASSWORD_RESET_MESSAGE)
        return redirect(url_for('.login_user'))

    # User requests password reset form.
    return render_template('users/reset_password_form.html', token=token)


@user_blueprint.route('/update_profile', methods=['GET', 'POST'])
@requires_login
def update_profile(user=None):

    if request.method == 'POST':

        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        user.update_user_profile(username, email, password)
        if email:
            session['email'] = email

        flash(PROFILE_UPDATED_MESSAGE)
        return redirect(url_for("spreadsheets.display_spreadsheets"))

    return render_template('users/profile_form.html', username=user.username, email=user.email)


@user_blueprint.route('/display_users', methods=['GET'])
@requires_admin
def display_users():
    """
    Administrative function only - displays a list of the site users.  Additionally, the number of
    spreadsheets owned by each user is determined and displayed.
    """
    users = User.find_all_users()
    user_counts_map = User.spreadsheet_counts()
    return render_template('users/display_users.html', users=users, user_counts_map=user_counts_map)


@user_blueprint.route('/delete', methods=['POST'])
@requires_admin
def delete():
    """
    Administrative ajax endpoint only - deletes the user provided and all of that user's spreadsheets.
    """
    user_id = json.loads(request.data).get('user_id', None)
    if not user_id:
        return jsonify({"error": MISSING_USER_ID_ERROR}), 400

    user = User.find_by_id(user_id)
    if user:
        user.delete()
    return '', 204


@user_blueprint.route('/confirm', methods=['POST'])
@requires_admin
def confirm():
    """
    Administrative function only - confirms the user provided, expiration notwithstanding
    """
    user_id = json.loads(request.data).get('user_id', None)
    if not user_id:
        return jsonify({"error": MISSING_USER_ID_ERROR}), 400

    # Visitors do need confirmations as they do not log in.
    user = User.find_by_id(user_id)
    if user and not user.is_visitor() and not user.activated:
        user.activated = True
        user.save_to_db()
        return jsonify({'confirmed': True})


@user_blueprint.route('/confirm_user/<string:token>', methods=['GET'])
def confirm_user(token):

    # The token must be valid and not yet expired.  Cannot directly send user to resend confirmation page because
    # we don't have the user's email.  So he/she will need to log in to be invited to resend a confirmation email.
    user = User.verify_user_token(token)
    if not user:
        flash(CONFIRMATION_TOKEN_EXPIRED)
        return redirect(url_for('.login_user'))

    # Confirmation request redundant - user already activated.
    if user.activated:
        flash(ALREADY_ACTIVATED_MESSAGE)
        return redirect(url_for('.login_user'))

    # Confirmation email accepted - activate and log in user.
    user.activated = True
    user.save_to_db()
    session['email'] = user.email
    session['visitor'] = user.is_visitor()
    flash(f"Your registration as '{user.username}' has been confirmed through your email { user.email }.")
    return redirect(url_for('spreadsheets.load_spreadsheet'))


@user_blueprint.route('/resend_confirmation', methods=['GET','POST'])
def resend_confirmation():
    """
    Standard endpoint - method is called when a user, invited to resend a confirmation email, elects to do just that.  The
    user's email is returned as a hidden form field.
    """

    if request.method == 'POST':

        email = request.form['email']
        user = User.find_by_email(email)

        # Bogus request - possibly a hacker exploring
        if not user:
            flash(ACCOUNT_NOT_FOUND_MESSAGE)
            return redirect(url_for('.register_user'))

        # Redundant confirmation request - user may have gotten to resend page and then found and clicked the email
        # link before making this request.
        if user.activated:
            flash(ALREADY_ACTIVATED_MESSAGE)
            return redirect(url_for('.login_user'))

        # If unable to send an email - user is invited to register at a later date.
        errors = user.send_confirmation_email()
        if errors:
            flash(errors)
            return redirect(url_for('.register_user'))

        # Confirmation sent
        flash(CONFIRMATION_SENT_MESSAGE)
        return redirect(url_for('spreadsheets.load_spreadsheet'))

    email = request.args['email']
    return render_template('users/resend_confirmation_form.html', email=email)