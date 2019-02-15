from flask import Blueprint, request, session, url_for, redirect, render_template
from models.users.user import User

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
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        user, status, messages = User.register_user(username, email, password)

        # Either user filled out the form incorrectly (possibly duplicate email or username or a required entry left
        # empty) or no confirmation email could be sent.
        if status == 'error':
            return render_template('users/registration_form.html',
                                   username=username, email=email,
                                   messages=messages, status=status)

        # User already registered but not activated.  May have ignored or not received confirmation email.
        # Invited user to check email or resend the confirmation email.
        if status == 'unconfirmed':
            return render_template('confirmations/resend_confirmation_form.html',
                                   confirmation_id=user.most_recent_confirmation.id,
                                   email=user.email,
                                   messages=messages, status=status)

        # User already registered and activated.  Send user to login page.
        if status == 'confirmed':
            return render_template('users/login_form.html', messages=messages, status=status,
                                   username = user.username)

        # User successfully registered and email sent.
        return render_template('confirmations/confirmation_sent.html', email = email)

    else:

        # User requests registration form.
        return render_template('users/registration_form.html')

@user_blueprint.route('/login', methods=['GET','POST'])
def login_user():
    """
    Handled user login.  The GET method requests the form.  The POST method attempts to process the user's input.
    A successful login takes the user back to the spreadsheet loading form page.  A login that is unsuccessful owing
    to an empty field or invalid credentials is returned to the login form with errors noted.  A login that is
    unsuccessful because the user's account is not yet activated, takes the user to the resend confirmation page
    where the user may resend a confirmation email.
    """

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user, status, messages = User.login_user(username, password)

        # User did not log in correctly - empty field or invalid credentials.  Return user to login form and note
        # errors.
        if status == 'error':
            return render_template('users/login_form.html', username = username, messages = messages, status = status)

        # User's account is not yet activated - possibly user ignored confirmation email or never received it.
        # Invite user to resend confirmation email.
        if status == 'unconfirmed':
            return render_template('confirmations/resend_confirmation_form.html',
                                    messages = messages,
                                    email = user.email,
                                    confirmation_id = user.most_recent_confirmation.id)

        # Log in user and redirect to the spreadsheet loading form.
        if user:
            session['email'] = user.email
        return redirect(url_for("spreadsheets.load_spreadsheet"))

    else:

        # User requests login form.
        return render_template('users/login_form.html')

@user_blueprint.route('/logout', methods=['GET'])
def logout_user():
    """
    Removes the user's email from the session, thereby logging the user off.
    :return: Returning user to spreadsheet upload form in lieu of a home page
    """

    session['email'] = None
    return render_template('spreadsheets/spreadsheet_upload_form.html')
