from flask import Blueprint, session, render_template, redirect, url_for, request

from models.confirmations.confirmation import Confirmation
from models.users.user import User

confirmation_blueprint = Blueprint('confirmations', __name__)

@confirmation_blueprint.route('/confirm_user/<string:confirmation_id>', methods=['GET'])
def confirm_user(confirmation_id):
    error = False
    messages = []
    confirmation = Confirmation.find_by_id(confirmation_id)
    if not confirmation:
        messages.append("No such account was found.  Please register.")
        return render_template('users/registration_form.html', messages=messages)
    if confirmation.expired:
        messages.append("Your confirmation email has expired.")
        return render_template('confirmations/resend_confirmation_form.html',
                               confirmation_id = confirmation.id,
                               email = confirmation.user.email,
                               messages = messages )
    if confirmation.confirmed:
        messages.append("You are already activated.  If you are still unable to log in, please communicate with us.")
        return render_template('users/login_form.html', messages=messages)
    confirmation.confirmed = True
    confirmation.save_to_db()
    user = confirmation.user
    session['email'] = user.email
    return render_template('confirmations/user_confirmed.html', username=user.username, email=user.email)

@confirmation_blueprint.route('/resend_confirmation', methods=['POST'])
def resend_confirmation():
    error = False
    messages = []
    confirmation_id = request.form['confirmation_id']
    confirmation = Confirmation.find_by_id(confirmation_id)
    if not confirmation or not confirmation.user:
        messages.append("No such account was found.  Please register.")
        return render_template('users/registration_form.html', messages=messages)
    else:
        confirmation = confirmation.user.most_recent_confirmation
        user = confirmation.user
        if confirmation:
            if confirmation.confirmed:
                messages.append("You are already activated.  Please communicate with us if you still unable to log in.")
                return render_template('users/login_form.html', messages=messages)
            confirmation.force_to_expire()
        new_confirmation = Confirmation(user.id)
        new_confirmation.save_to_db()
        error, messages = user.send_confirmation_email()
    if error:
        return render_template('users/login_form.html', messages=messages)
    return render_template('confirmations/confirmation_sent.html', email=user.email)
