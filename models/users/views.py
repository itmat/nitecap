from flask import Blueprint, request, session, url_for, redirect, render_template
from models.users.user import User

user_blueprint = Blueprint('users', __name__)

@user_blueprint.route('/register', methods=['GET','POST'])
def register_user():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        user, error, messages = User.register_user(username, email, password)
        if error:
            return render_template('users/registration_form.html', username=username, email=email, messages=messages)
        if user:
            return render_template('users/registration_form.html', confirmation_sent=True, username=username, email=email)
        return redirect(url_for("spreadsheet.load_spreadsheet"))
    else:
        return render_template('users/registration_form.html')

@user_blueprint.route('/login', methods=['GET','POST'])
def login_user():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user, error, messages = User.login_user(username, password)
        if error:
            if user:
                return render_template('confirmations/resend_confirmation_form.html',
                                       messages = messages,
                                       email = user.email,
                                       confirmation_id = user.most_recent_confirmation.id)
            return render_template('users/login_form.html', username=username, messages=messages)
        if user:
            session['email'] = user.email
        return redirect(url_for("spreadsheets.load_spreadsheet"))
    else:
        return render_template('users/login_form.html')

@user_blueprint.route('/logout', methods=['GET'])
def logout_user():
    session['email'] = None
    return render_template('spreadsheets/spreadsheet_upload_form.html')
