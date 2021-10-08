import json
from functools import wraps

from flask import session, request, url_for, flash, current_app, jsonify
from werkzeug.utils import redirect

from models.users.user import User
from models.shares import Share

MUST_BE_LOGGED_IN_MESSAGE = "You must be logged in to perform this activity."
MUST_HAVE_ACCOUNT_MESSAGE = "You must be logged in or working on a spreadsheet to perform this activity."
LOGIN_ENDPOINT = 'users.login_user'


def requires_account(func):
    """
    Insure that the given wrapped function is accessible only to users with accounts (either visitor's who have
    a spreadsheet or a logged in user.
    :param func: the wrapped function
    :return: decorated_function with 'user' : user in the function's kwargs or a redirect to the login page if the
    account requirement is not satisfied.
    """
    @wraps(func)
    def decorated_function(*args, **kwargs):
        if 'email' not in session.keys() or session['email'] is None:
            flash(MUST_HAVE_ACCOUNT_MESSAGE)
            return redirect(url_for(LOGIN_ENDPOINT, next=request.path))
        user = User.find_by_email(session['email'])
        if not user:
            flash(MUST_HAVE_ACCOUNT_MESSAGE)
            return redirect(url_for(LOGIN_ENDPOINT, next=request.path))
        kwargs['user'] = user
        return func(*args, **kwargs)
    return decorated_function


def requires_login(func):
    """
    Insures that the given wrapped function is accessible only to logged in users.
    :param func: the wrapped function
    :return: decorated_function with 'user' : user in the function's kwargs or a redirect to the login page if the
    logged in requirement is not satisfied.
    """
    @wraps(func)
    def decorated_function(*args, **kwargs):
        if 'email' not in session.keys() or session['email'] is None:
            flash(MUST_BE_LOGGED_IN_MESSAGE)
            return redirect(url_for(LOGIN_ENDPOINT, next=request.path))
        user = User.find_by_email(session['email'])
        if not user or user.is_visitor():
            flash(MUST_BE_LOGGED_IN_MESSAGE)
            return redirect(url_for(LOGIN_ENDPOINT, next=request.path))
        kwargs['user'] = user
        return func(*args, **kwargs)
    return decorated_function


def requires_admin(func):
    """
    Insures that the given wrapped function is accessible only to logged in users identified as ADMIN users.
    :param func: the wrapped function
    :return: decorated function with 'user' : user in the function's kwargs or a redirect to the login page if the
    logged in admin requirement is not satisfied.
    """
    @wraps(func)
    def decorated_function(*args, **kwargs):
        if 'email' not in session.keys() or session['email'] is None:
            flash(MUST_BE_LOGGED_IN_MESSAGE)
            return redirect(url_for(LOGIN_ENDPOINT, next=request.path))
        if session['email'] not in current_app.config['ADMIN_LIST']:
            flash(MUST_BE_LOGGED_IN_MESSAGE)
            return redirect(url_for(LOGIN_ENDPOINT, next=request.path))
        user = User.find_by_email(session['email'])
        if not user:
            flash(MUST_BE_LOGGED_IN_MESSAGE)
            return redirect(url_for(LOGIN_ENDPOINT, next=request.path))
        return func(*args, **kwargs)
    return decorated_function


def ajax_requires_account(func):
    """
    Insures that the given wrapped function is accessible only to users with accounts (either visitor's who have
    a spreadsheet or a logged in user.  Applies to ajax calls.
    :param func: the wrapped function
    :return: decorated_function with 'user' : user in the function's kwargs or an 401 response.
    """
    @wraps(func)
    def decorated_function(*args, **kwargs):
        if 'email' not in session.keys() or session['email'] is None:
            return jsonify({"error": MUST_HAVE_ACCOUNT_MESSAGE}), 401
        user = User.find_by_email(session['email'])
        if not user:
            return jsonify({"error": MUST_HAVE_ACCOUNT_MESSAGE}), 401
        kwargs['user'] = user
        return func(*args, **kwargs)
    return decorated_function

ANALYSIS_STATUS_ENDPOINT = "/analysis/<analysisId>/status"
ANALYSIS_RESULT_ENDPOINT = "/analysis/<analysisId>/results/url"
ANALYSIS_PARAMETERS_ENDPOINT = "/analysis/<analysisId>/parameters"

from computation.utils import get_spreadsheets_associated_with_analysis

def ajax_requires_account_or_share(func):
    """
    Insures that the given wrapped function is accessible only to users with accounts (either visitor's who have
    a spreadsheet or a logged in user.  Applies to ajax calls.
    If a share_token is in the request, then the token is checked whether it matches the requested spreadsheet_ids .
    Request is expected to have 'spreadsheet_ids' member or else this check is unnecessary
    :param func: the wrapped function
    :return: decorated_function with 'user' : user in the function's kwargs or an 401 response.
    """
    @wraps(func)
    def decorated_function(*args, **kwargs):
        spreadsheet_ids = []
        if str(request.url_rule) in [ANALYSIS_STATUS_ENDPOINT, ANALYSIS_RESULT_ENDPOINT, ANALYSIS_PARAMETERS_ENDPOINT]:
            share_token = request.headers.get('Authorization', '')
            if share_token:
                # TODO: Refactor needed so that error handling is taken care of
                user_id = Share.find_by_id(share_token).user_id
                analysis_id = request.view_args['analysisId']
                spreadsheet_ids = get_spreadsheets_associated_with_analysis(user_id, analysis_id)
        else:
            data = json.loads(request.data)
            spreadsheet_ids = data['spreadsheet_ids'] if 'spreadsheet_ids' in data else [data['spreadsheetId']]
            share_token = data.get("share_token", '')

        if share_token != '':
            # Check sharing token matches the target spreadsheets and has a user
            try:
                share = Share.find_by_id(share_token)
            except Exception as e:
                current_app.logger.error(f"Invalid share URL identified with token {share_token}");
                current_app.logger.error(e)
                return jsonify({"error": "The URL you received does not work.  It may have been mangled in transit.  Please request "
                              "another share"}), 401
            sharing_user = User.find_by_id(share.user_id)
            shared_spreadsheet_ids = [int(id) for id in share.spreadsheet_ids_str.split(',')]
            if set(spreadsheet_ids).issubset(shared_spreadsheet_ids):
                # Spreadsheets match, grant the access under the sharing user's account
                kwargs['user'] = sharing_user
            else:
                return jsonify({"error": "The URL you received does not work.  It may have been mangled in transit.  Please request "
                              "another share"}), 401
        else:
            # No share, verify actual user
            if 'email' not in session.keys() or session['email'] is None:
                return jsonify({"error": MUST_HAVE_ACCOUNT_MESSAGE}), 401
            user = User.find_by_email(session['email'])
            if not user:
                return jsonify({"error": MUST_HAVE_ACCOUNT_MESSAGE}), 401
            kwargs['user'] = user
        return func(*args, **kwargs)
    return decorated_function


def ajax_requires_login(func):
    """
    Insures that the given wrapped function is accessible only to logged in users.  Applies to ajax calls.
    :param func: the wrapped function
    :return: decorated_function with 'user' : user in the function's kwargs or a 401 response.
    """
    @wraps(func)
    def decorated_function(*args, **kwargs):
        if 'email' not in session.keys() or session['email'] is None:
            return jsonify({"error": MUST_HAVE_ACCOUNT_MESSAGE}), 401
        user = User.find_by_email(session['email'])
        if not user or user.is_visitor():
            return jsonify({"error": MUST_HAVE_ACCOUNT_MESSAGE}), 401
        kwargs['user'] = user
        return func(*args, **kwargs)
    return decorated_function


def ajax_requires_admin(func):
    """
    Insures that the given wrapped function is accessible only to logged in users identified as ADMIN users.  Applies
    to ajax calls.
    :param func: the wrapped function
    :return: decorated function with 'user' : user in the function's kwargs or a 401 response.
    """
    @wraps(func)
    def decorated_function(*args, **kwargs):
        if 'email' not in session.keys() or session['email'] is None:
            return jsonify({"error": MUST_HAVE_ACCOUNT_MESSAGE}), 401
        if session['email'] not in current_app.config['ADMIN_LIST']:
            return jsonify({"error": MUST_HAVE_ACCOUNT_MESSAGE}), 401
        user = User.find_by_email(session['email'])
        if not user:
            return jsonify({"error": MUST_HAVE_ACCOUNT_MESSAGE}), 401
        return func(*args, **kwargs)
    return decorated_function
