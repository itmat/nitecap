from flask import Blueprint, session, render_template, redirect, url_for, request, flash

from models.confirmations.confirmation import Confirmation
from models.users.user import User

confirmation_blueprint = Blueprint('confirmations', __name__)

@confirmation_blueprint.route('/confirm_user/<string:confirmation_id>', methods=['GET'])
def confirm_user(confirmation_id):
    """
    This GET method is called when the user clicks on the link provided in the confirmation email.  The link contains
    the id of the last confirmation created for the user (the user may have prior confirmations owing to recovery
    from expirations or failed deliveries).  A successful request occurs when the confirmation associated with the
    given id is found and found not to be expired.  In that case, the user is automatically logged in and directed to
    a user confirmed page.  If the confirmation id does not belong to any confirmation, the user is taken to the
    registration page.  If the user is already activated, the user is taken to the login page.  If the user's
    confirmation has expired, the user is invited to resend the confirmation email.

    :param confirmation_id:  id for the user's current confirmation
    """

    messages = []
    confirmation = Confirmation.find_by_id(confirmation_id)

    # Bogus confirmation.  Likely sent by a hacker.
    if not confirmation:
        messages.append("No such account was found.  Please register.")
        return render_template('users/registration_form.html', messages = messages, status = 'error')

    # Dealing with the possibility that the user is clicking a link in an old confirmation email.  We use it to
    # find the current confirmation since that's the one that counts.
    confirmation = confirmation.user.most_recent_confirmation

    # Confirmation request redundant - user already activated.
    if confirmation.confirmed:
        flash("You are already activated.  If you are still unable to log in, please communicate with us.")
        return redirect(url_for('users.login_user'))

    # Confirmation email expired - offer to resend.
    if confirmation.expired:
        flash("Sorry.  Your confirmation email has expired.")
        return render_template('confirmations/resend_confirmation_form.html',
                               confirmation_id = confirmation.id, email = confirmation.user.email)

    # Confirmation email accepted - activate and log in user.
    confirmation.confirmed = True
    confirmation.save_to_db()
    user = confirmation.user
    session['email'] = user.email
    flash(f"Your registration as '{user.username}' has been confirmed through your email { user.email }.")
    return redirect(url_for('spreadsheets.load_spreadsheet'))

@confirmation_blueprint.route('/resend_confirmation', methods=['POST'])
def resend_confirmation():
    """
    This POSt method is called when a user, invited to resend a confirmation email, elects to do just that.
    """

    messages = []
    errors = []
    status = None
    confirmation_id = request.form['confirmation_id']
    confirmation = Confirmation.find_by_id(confirmation_id)

    # Bogus request - possibly a hacker exploring
    if not confirmation or not confirmation.user:
        errors.append("No such account was found.  Please register.")
        return render_template('users/registration_form.html', errors = errors)

    # Using any user confirmation (past or present) to find the most current confirmation
    confirmation = confirmation.user.most_recent_confirmation
    user = confirmation.user

    # Theoretically, this should always be true
    if confirmation:

        # Redundant confirmation request - user may have gotten to resend page and then found and clicked the email
        # link before making this request.
        if confirmation.confirmed:
            flash("Your account is already activated.  Please communicate with us if you still unable to log in.")
            return render_template('users/login_form.html')

        # Expire the most recent confirmation before issuing a new one.
        confirmation.force_to_expire()

    new_confirmation = Confirmation(user.id)
    new_confirmation.save_to_db()

    # Unable to send an email.  User invited to register at a later date.
    errors = user.send_confirmation_email()
    if errors:
        return render_template('users/registration_form.html', errors = errors)

    # Confirmation sent
    flash(f"Your confirmation email has been sent.  Click on the link it contains to activate your account.")
    return redirect(url_for('spreadsheets.load_spreadsheet'))
