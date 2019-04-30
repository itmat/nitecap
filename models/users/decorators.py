from functools import wraps

from flask import session, request, url_for, flash, current_app
from werkzeug.utils import redirect


def requires_login(func):
    @wraps(func)
    def decorated_function(*args, **kwargs):
        if 'email' not in session.keys() or session['email'] is None:
            flash("You must be logged in to perform this activity.")
            return redirect(url_for('users.login_user', next=request.path))
        return func(*args, **kwargs)
    return decorated_function


def requires_admin(func):
    @wraps(func)
    def decorated_function(*args, **kwargs):
        if 'email' not in session.keys() or session['email'] is None:
            flash("You must be logged in to perform this activity.")
            return redirect(url_for('users.login_user', next=request.path))
        current_app.logger.info(f"{session['email']} and {current_app.config['ADMIN_LIST']}")
        if session['email'] not in current_app.config['ADMIN_LIST']:
            flash("You must be an admin in to perform this activity.")
            return redirect(url_for('users.login_user', next=request.path))
        return func(*args, **kwargs)
    return decorated_function