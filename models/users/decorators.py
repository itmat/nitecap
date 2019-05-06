from functools import wraps

from flask import session, request, url_for, flash, current_app
from werkzeug.utils import redirect

from models.users.user import User


def requires_account(func):
    """
    Insure that the given wrapped function is accessible only to users with accounts (either visitor's who have
    a spreadsheet or a logged in user.
    :param func: the wrapped function
    :return: decorated_function with 'user' : user in the function's kwargs.
    """
    @wraps(func)
    def decorated_function(*args, **kwargs):
        if 'visitor' not in session.keys() or 'email' not in session.keys() or session['email'] is None:
            flash("You must be logged in or working on a spreadsheet to perform this activity.")
            return redirect(url_for('users.login_user', next=request.path))
        user = User.find_by_email(session['email'])
        if not user:
            flash("You must be logged in or working on a spreadsheet to perform this activity.")
            return redirect(url_for('users.login_user', next=request.path))
        kwargs['user'] = user
        return func(*args, **kwargs)

    return decorated_function


def requires_login(func):
    """
    Insures that the given wrapped function is accessible only to logged in users.
    :param func: the wrapped function
    :return: decorated_function with 'user' : user in the function's kwargs.
    """
    @wraps(func)
    def decorated_function(*args, **kwargs):
        if 'visitor' not in session.keys() or session['visitor'] or \
           'email' not in session.keys() or session['email'] is None:
            flash("You must either be logged in to perform this activity.")
            return redirect(url_for('users.login_user', next=request.path))
        user = User.find_by_email(session['email'])
        if not user:
            flash("You must be logged in to perform this activity.")
            return redirect(url_for('users.login_user', next=request.path))
        kwargs['user'] = user
        return func(*args, **kwargs)
    return decorated_function


def requires_admin(func):
    """
    Insures that the given wrapped function is accessible only to logged in users identified as ADMIN users.
    :param func: the wrapped function
    :return: decorated function
    """
    @wraps(func)
    def decorated_function(*args, **kwargs):
        if 'email' not in session.keys() or session['email'] is None:
            flash("You must be logged in to perform this activity.")
            return redirect(url_for('users.login_user', next=request.path))
        if session['email'] not in current_app.config['ADMIN_LIST']:
            flash("You must be an admin in to perform this activity.")
            return redirect(url_for('users.login_user', next=request.path))
        user = User.find_by_email(session['email'])
        if not user:
            flash("You must be logged in to perform this activity.")
            return redirect(url_for('users.login_user', next=request.path))
        return func(*args, **kwargs)
    return decorated_function