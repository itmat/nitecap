import json
import os
import uuid
from pathlib import Path
import io

import magic
import numpy
import pandas as pd
import pyarrow
import pyarrow.parquet
from flask import Blueprint, request, session, url_for, redirect, render_template, send_file, jsonify
from flask import Blueprint, request, session, url_for, redirect, render_template, send_file, jsonify, flash
from flask import current_app
from sklearn.decomposition import PCA

import constants
import nitecap
from exceptions import NitecapException
from models.spreadsheets.spreadsheet import Spreadsheet
from models.users.decorators import requires_login, requires_admin, requires_account, ajax_requires_login, \
    ajax_requires_account, ajax_requires_admin
from models.users.user import User
from timer_decorator import timeit

spreadsheet_blueprint = Blueprint('spreadsheets', __name__)

MANAGE_OWN_SPREADSHEETS_MESSAGE = "You may only manage your own spreadsheets."
MISSING_SPREADSHEET_ID_ERROR = "No spreadsheet was provided."
SPREADSHEET_NOT_FOUND_MESSAGE = "No such spreadsheet can be found."

@spreadsheet_blueprint.route('/load_spreadsheet', methods=['GET', 'POST'])
@timeit
def load_spreadsheet():
    """
    Standard endpoint - uploads a new spreadsheet.  Extensive validation and evaluation of mime types.  If the user
    uploading the spreadsheet is not logged in, a visitor account is assigned to the user.
    """
    current_app.logger.info('Loading spreadsheet')
    if request.method == 'POST':

        # Collect and validate the form data
        descriptive_name, days, timepoints, repeated_measures, header_row, upload_file, errors =\
            validate_spreadsheet_upload_form(request.form, request.files)
        if errors:
            return render_template('spreadsheets/spreadsheet_upload_form.html', errors=errors,
                                   descriptive_name=descriptive_name, days=days,
                                   timepoints=timepoints, repeated_measures=repeated_measures, header_row=header_row)

        # Rename the uploaded file to avoid any naming collisions and save it
        extension = Path(upload_file.filename).suffix
        new_filename = uuid.uuid4().hex + extension
        file_path = os.path.join(os.environ.get('UPLOAD_FOLDER'), new_filename)
        upload_file.save(file_path)

        # If the mime type validation fails, remove the uploaded file from the disk
        file_mime_type, errors = validate_mime_type(file_path)
        if errors:
            os.remove(file_path)
            return render_template('spreadsheets/spreadsheet_upload_form.html', errors=errors,
                                   descriptive_name=descriptive_name, days=days,
                                   timepoints=timepoints, repeated_measures=repeated_measures, header_row=header_row)

        # Identify any logged in user or current visitor accout so that ownership of the spreadsheet is established.
        user_id = None
        user_email = session['email'] if 'email' in session else None
        if user_email:
            user = User.find_by_email(user_email)
            user_id = user.id if user else None
        # If user is not logged in or has a current visitor accout, assign a visitor account to protect user's
        # spreadsheet ownership.
        else:
            user = User.create_visitor()
            if user:
                # Visitor's session has a fixed expiry date.
                # session.permanent = True
                session['email'] = user.email
                session['visitor'] = True
                user_id = user.id

        # If we have no logged in user and a visitor account could not be generated, we have an internal
        # problem.
        if not user:
            errors.append("We are unable to load your spreadsheet at the present time.  Please try again later")
            current_app.logger.error("Spreadsheet load issue, unable to identify or generate a user.")
            return render_template('spreadsheets/spreadsheet_upload_form.html', errors=errors,
                                   descriptive_name=descriptive_name, days=days,
                                   timepoints=timepoints, repeated_measures=repeated_measures, header_row=header_row)

        # For some files masquerading as one of the acceptable file types by virtue of its file extension, we
        # may only be able to identify it when pandas fails to parse it while creating a spreadsheet object.
        # We throw the file away and report the error.
        try:
            spreadsheet = Spreadsheet(descriptive_name=descriptive_name,
                                      days=days,
                                      timepoints=timepoints,
                                      repeated_measures=repeated_measures,
                                      header_row=header_row,
                                      original_filename=upload_file.filename,
                                      file_mime_type=file_mime_type,
                                      uploaded_file_path=file_path,
                                      user_id=user_id)
        except NitecapException as ne:
            current_app.logger.error(f"NitecapException {ne}")
            os.remove(file_path)
            errors.append(ne.message)
            return render_template('spreadsheets/spreadsheet_upload_form.html', errors=errors,
                                   days=days, timepoints=timepoints)

        # Save the spreadsheet metadata to the database.
        spreadsheet.save_to_db()

        # Continue to form that labels the spreadsheet columns.
        return redirect(url_for('.label_columns', spreadsheet_id=spreadsheet.id))

    return render_template('spreadsheets/spreadsheet_upload_form.html')


@timeit
def validate_spreadsheet_upload_form(form_data, files):
    """
    Helper method to collect form data and validate it
    :param form_data: the form dictionary from requests
    :param files: the files dictionary from requests
    :return: a tuplbe consisting of the form data and an array of error msgs.  An empty array indicates no errors
    """

    # Gather data
    descriptive_name = form_data.get('descriptive_name', None)
    days = form_data.get('days', None)
    timepoints = form_data.get('timepoints', None)
    repeated_measures = form_data.get('repeated_measures', 'n')
    repeated_measures = True if repeated_measures == 'y' else False
    header_row = form_data.get('header_row', None)
    upload_file = files.get('upload_file', None)

    # Check data for errors
    errors = []
    if not descriptive_name or len(descriptive_name) > 250:
        errors.append(f"A descriptive name is required and may be no longer than 250 characters.")
    if not days or not days.isdigit():
        errors.append(f"The value for days is required and must be a positve integer.")
    if not timepoints or not timepoints.isdigit():
        errors.append(f"The value for timepoints is required and must be a positve integer.")
    if not header_row or not header_row.isdigit():
        errors.append(f"The value of the header row is required and must be a positive integer.")
    if not upload_file:
        errors.append(f'No spreadsheet file was provided.')
    else:
        if not len(upload_file.filename):
            errors.append('No spreadsheet file was provided.')
        if not allowed_file(upload_file.filename):
            errors.append(f"File must be one of the following types: {', '.join(constants.ALLOWED_EXTENSIONS)}")
    return descriptive_name, days, timepoints, repeated_measures, header_row, upload_file, errors


def allowed_file(filename):
    """
    Helper method to establish whether the filename of the uploaded file contains an acceptable suffix.
    :param filename: uploaded file filename
    :return: True if the suffix is allowed and false otherwise
    """
    extension = Path(filename).suffix
    return extension.lower() in constants.ALLOWED_EXTENSIONS


@timeit
def validate_mime_type(file_path):
    """
    Helper method to determine the mime type of the uploaded file.  It appears that the mime type can only be verified
    for a saved file.  So the path to the saved uploaded file is provided. A check is made that the mime type is among
    those allowed for an uploaded spreadsheet.  The mime type of underlying file that is compressed is also checked.
    :param file_path: file path of saved uploaded file
    :return: A tuple, containing the discovered mime type and an array containing an error message if an error was
     found and an empty array otherwise
    """

    # It appears that we can only verify the mime type of a file once saved.  We will delete it if it is found not
    # to be one of the accepted file mime types.
    errors = []
    disallowed_mime_type = f"Only comma or tab delimited files or Excel spreadsheets are accepted.  " \
                           f"They may be gzipped."
    x = magic.Magic(mime=True)
    z = magic.Magic(mime=True, uncompress=True)
    file_mime_type = x.from_file(file_path)
    current_app.logger.info(f"Upload file type: {file_mime_type}")
    if file_mime_type not in constants.ALLOWED_MIME_TYPES:
        errors.append(disallowed_mime_type)
    elif file_mime_type in constants.COMPRESSED_MIME_TYPES:
        file_mime_type = z.from_file(file_path)
        if file_mime_type not in constants.ALLOWED_MIME_TYPES:
            errors.append(disallowed_mime_type)
    return file_mime_type, errors


def access_not_permitted(endpoint, user, spreadsheet_id):
    """
    Helper method for situation where user attempts to access a spreadsheet that does not belong to him/her.
    :param user: object of user attempting the access
    :param visitor: whether or not the user is a visitor (the page a visitor is dropped into is different from
    that of a logged in user
    :param spreadsheet_id: the id of the spreadsheet the user is attempting to access.
    :return: an appropriate page to which to return the user.
    """
    flash(MANAGE_OWN_SPREADSHEETS_MESSAGE)
    current_app.logger.warn(f"User {user.id} attempted to apply the endpoint {endpoint} to "
                            f"spreadsheet {spreadsheet_id}")
    if user.is_visitor():
        return render_template(url_for('.load_spreadsheet'))
    return redirect(url_for('.display_spreadsheets'))


@spreadsheet_blueprint.route('label_columns/<int:spreadsheet_id>', methods=['GET', 'POST'])
@timeit
@requires_account
def label_columns(spreadsheet_id, user=None):
    """
    Standard endpoint - labels spreadsheet columns appropriately.  This method is available to any user with an
    account (standard user or visitor).
    :param spreadsheet_id: id of spreadsheet having columns to be labelled.
    :param user:  Returned by the decorator.  Account bearing user is required.
    """

    errors = []
    spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)

    # If the spreadsheet is not verified as owned by the user, the user is either returned to the his/her
    # spreadsheet list (in the case of a logged in user) or to the upload form (in the case of a visitor).
    if not spreadsheet:
        return access_not_permitted(label_columns.__name__, user, spreadsheet_id)

    # Populate the spreadsheet object with additional data
    spreadsheet.init_on_load()

    # Column label form submitted.
    if request.method == 'POST':
        column_labels = list(request.form.values())

        # If label assignments are improper, the user is returned to the column label form and invited to edit.
        error, messages = spreadsheet.validate(column_labels)
        errors.extend(messages)
        if error:
            return render_template('spreadsheets/spreadsheet_columns_form.html', spreadsheet=spreadsheet, errors=errors)

        spreadsheet.identify_columns(column_labels)
        spreadsheet.set_ids_unique()
        spreadsheet.compute_nitecap()
        spreadsheet.save_to_db()
        return redirect(url_for('.show_spreadsheet', spreadsheet_id=spreadsheet.id))

    return render_template('spreadsheets/spreadsheet_columns_form.html', spreadsheet=spreadsheet, errors=errors)

@spreadsheet_blueprint.route('/show_spreadsheet/<int:spreadsheet_id>', methods=['GET'])
@requires_account
@timeit
def show_spreadsheet(spreadsheet_id, user=None):
    """
    Standard endpoint - retrieves the spreadsheet id from the url and pulls up the associated display (graphics and tables).  This
    method is available to any user with an account (standard user or visitor).
    :param spreadsheet_id: the id of the spreadsheet whose results are to be displayed.
    :param user:  Returned by the decorator.  Account bearing user is required.
    """

    spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)

    if not spreadsheet:
        return access_not_permitted(show_spreadsheet.__name__, user, spreadsheet_id)

    # Populate
    spreadsheet.init_on_load()

    # In the case of an incompletely processed spreadsheet (e.g., the user uploaded a spreadsheet, got distracted and
    # closed the browser only later to see the spreadsheet in his/her spreadsheet listing), the user must still match
    # days and timepoints to columns.
    if not spreadsheet.column_labels:
        errors = [f"Days/timepoint were not yet matched to columns for spreadsheet '{spreadsheet.descriptive_name}'.  "
                  f"You may have skipped a step.  Please re-edit your data."]
        if user.is_visitor():
            render_template('spreadsheets/spreadsheet_columns_form.html', errors=errors)
        return render_template('spreadsheets/user_spreadsheets.html', user=user, errors=errors)

    data = spreadsheet.get_raw_data()

    max_value_filter = spreadsheet.max_value_filter if spreadsheet.max_value_filter else 'null'
    ids = json.dumps(spreadsheet.get_ids())

    args = dict( data=data.to_json(orient='values'),
                 x_values=spreadsheet.x_values,
                 x_labels=spreadsheet.x_labels,
                 x_label_values=spreadsheet.x_label_values,
                 qs=spreadsheet.df.nitecap_q.to_json(orient="values"),
                 ps=spreadsheet.df.nitecap_p.to_json(orient="values"),
                 amplitudes=spreadsheet.df.amplitude.to_json(orient="values"),
                 peak_times=spreadsheet.df.peak_time.to_json(orient="values"),
                 anova_ps=spreadsheet.df.anova_p.to_json(orient="values"),
                 anova_qs=spreadsheet.df.anova_q.to_json(orient="values"),
                 filtered=spreadsheet.df.filtered_out.to_json(orient="values"),
                 ids=ids,
                 column_pairs=spreadsheet.column_pairs,
                 breakpoint=spreadsheet.breakpoint if spreadsheet.breakpoint is not None else 0,
                 descriptive_name=spreadsheet.descriptive_name,
                 timepoints_per_day=spreadsheet.timepoints,
                 spreadsheet_id=spreadsheet_id,
                 spreadsheet_note=spreadsheet.note,
                 vistor=user.is_visitor(),
                 max_value_filter=max_value_filter)

    return render_template('spreadsheets/spreadsheet_breakpoint_form.html',**args)


@spreadsheet_blueprint.route('/jtk', methods=['POST'])
@timeit
@ajax_requires_account
def get_jtk(user=None):

    spreadsheet_id = json.loads(request.data)['spreadsheet_id']

    if not spreadsheet_id:
        return jsonify({"error": MISSING_SPREADSHEET_ID_ERROR}), 400

    spreadsheet = Spreadsheet.find_by_id(spreadsheet_id)

    # Populate
    spreadsheet.init_on_load()

    jtk_ps, jtk_qs = spreadsheet.get_jtk()
    return jsonify({"jtk_ps": jtk_ps, "jtk_qs": jtk_qs})


@spreadsheet_blueprint.route('/display_spreadsheets', methods=['GET'])
@requires_login
def display_spreadsheets(user=None):
    """
    Standard endpoint - takes the logged in user to a listing of his/her spreadsheets.  The decorator assures that only
    logged in users may make such a request.
    :param user:  Returned by the decorator.  Logged in user is required.
    """

    current_app.logger.info(f"Displaying spreadsheets for user {user.username}")
    return render_template('spreadsheets/user_spreadsheets.html', user=user)


@spreadsheet_blueprint.route('/delete', methods=['POST'])
@ajax_requires_login
def delete(user=None):
    """
    AJAX endpoint - delete the user's spreadsheet data and its metadata.  The user must be logged in and own the
    spreadsheet given by the id provided.  The reference to the spreadsheet is first removed from the database and then
    the associated files are removed.  Any incomplete removal is reported to the user and logged.
    :param user:  Returned by the decorator.  Logged in user is required.
    :return: A successful ajax call returns nothing (just a 204 status code).
    """

    spreadsheet_id = json.loads(request.data).get('spreadsheet_id', None)

    if not spreadsheet_id:
        return jsonify({"error": MISSING_SPREADSHEET_ID_ERROR}), 400

    spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
    if not spreadsheet:
        current_app.logger.warn(f"User {user.id} attempted to delete spreadsheet {spreadsheet_id}")
        return jsonify({"error": MANAGE_OWN_SPREADSHEETS_MESSAGE}), 403

    try:
        spreadsheet.delete_from_db()
        os.remove(spreadsheet.file_path)
        os.remove(spreadsheet.uploaded_file_path)
    except Exception as e:
        current_app.logger.error(f"The data for spreadsheet {spreadsheet_id} could not all be successfully "
                                 f"expunged.", e)
        return jsonify({"error": 'The spreadsheet data may not have been all successfully removed'}), 500
    return '', 204


@spreadsheet_blueprint.route('/download/<int:spreadsheet_id>', methods=['GET'])
@requires_account
def download(spreadsheet_id, user=None):
    """
    Response to a request from the graphs page to download the spreadsheet whose id is in the session.  In this case,
    the user need not be logged in.  Nevertheless, the requested spreadsheet must be in the user's inventory.  In the
    case of a visitor, the spreadsheet must not be in the inventory of any logged in user.  If the user is authorized
    to download the spreadsheet and the file is available, the file representing the fully processed version of the
    spreadsheet is delivered as an attachment.
    :param user:  Returned by the decorator.  Account bearing user is required.
    """
    errors = []
    spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)

    if not spreadsheet:
            return access_not_permitted(download.__name__, user, spreadsheet_id)
    spreadsheet.init_on_load()
    txt_data = io.StringIO()
    spreadsheet.df.to_csv(txt_data, sep='\t')
    txt = txt_data.getvalue()
    byte_data = io.BytesIO(str.encode(txt))
    try:
        return send_file(byte_data, mimetype="text/plain", as_attachment=True, attachment_filename='processed_spreadsheet.txt')
    except Exception as e:
        errors.append("The processed spreadsheet data could not be downloaded.")
        current_app.logger.error(f"The processed spreadsheet data for spreadsheet {spreadsheet_id} could not be "
                                 f"downloaded.", e)
        return render_template('spreadsheets/spreadsheet_upload_form.html', errors=errors)

@spreadsheet_blueprint.route('/edit/<int:spreadsheet_id>', methods=['GET', 'POST'])
@requires_account
def edit_details(spreadsheet_id, user=None):
    """
    Standard endpoint - allows a logged in user to edit the details of an existing spreadsheet (e.g., name, # days, # timepoints, etc).  A
    check is made to insure that the spreadsheet id sent in the url identifies a spreadsheet in the logged in user's
    inventory.
    :param spreadsheet_id:  id to the spreadsheet whose details the logged in user wishes to edit.
    :param user:  Returned by the decorator.  Account bearing user is required.
    """
    errors = []

    # Insure user owns spreadsheet
    spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
    if not spreadsheet:
        return access_not_permitted(edit_details.__name__, user, spreadsheet_id)

    if request.method == "POST":
        descriptive_name = request.form['descriptive_name']
        days = request.form['days']
        timepoints = request.form['timepoints']
        repeated_measures = request.form['repeated_measures']
        repeated_measures = True if repeated_measures == 'y' else False
        header_row = request.form['header_row']

        if not descriptive_name or len(descriptive_name) > 250:
            errors.append(f"A descriptive name is required and may be no longer than 250 characters.")
        if not days.isdigit():
            errors.append(f"The value for days is required and must be a positve integer.")
        if not timepoints.isdigit():
            errors.append(f"The value for timepoints is required and must be a positve integer.")
        if not header_row or not header_row.isdigit():
            errors.append(f"The value of the header row is required and must be a positive integer.")
        if errors:
            return render_template('spreadsheets/edit_form.html', errors=errors,
                                   descriptive_name=descriptive_name,
                                   days=days,
                                   timepoints=timepoints,
                                   repeated_measures=repeated_measures,
                                   header_row=header_row)
        spreadsheet.descriptive_name = descriptive_name
        spreadsheet.days = days
        spreadsheet.timepoints = timepoints
        spreadsheet.repeated_measures = repeated_measures
        spreadsheet.header_row = header_row
        spreadsheet.save_to_db()
        return redirect(url_for('.edit_columns'))
    return render_template('spreadsheets/edit_form.html', spreadsheet_id=spreadsheet_id,
                           descriptive_name=spreadsheet.descriptive_name,
                           days=spreadsheet.days,
                           timepoints=spreadsheet.timepoints,
                           repeated_measures=spreadsheet.repeated_measures,
                           header_row=spreadsheet.header_row)

@spreadsheet_blueprint.route('/save_filters', methods=['POST'])
@ajax_requires_account
def save_filters(user=None):
    """
    AJAX endpoint - apply filters set on the graphs page.  Those filter values are also saved to the
    spreadsheet entry in the database.  The call may be made by both logged in users and visitors (annonymous user).
    :param user:  Returned by the decorator.  Account bearing user is required.
    :return: A json string containing filtered values along with associated q values and p values.
    """

    json_data = request.get_json()
    max_value_filter = json_data.get('max_value_filter', None)
    spreadsheet_id = json_data.get('spreadsheet_id', None)

    # Bad data
    if not spreadsheet_id:
        return jsonify({"error": MISSING_SPREADSHEET_ID_ERROR}), 400

    # Collect spreadsheet owned by user
    spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)

    # Attempt to access spreadsheet not owned.
    if not spreadsheet:
        current_app.logger.warn(f"User {user.id} attempted to save spreadsheet filters {spreadsheet_id}")
        return jsonify({"error": MANAGE_OWN_SPREADSHEETS_MESSAGE}), 403

    # Populate spreadsheet with raw data
    spreadsheet.init_on_load()

    spreadsheet.max_value_filter = float(max_value_filter) if max_value_filter else None
    spreadsheet.apply_filters()
    spreadsheet.save_to_db()

    response = jsonify({'qs': [x if x == x else None for x in list(spreadsheet.df.nitecap_q.values)],
                        'ps': [x if x == x else None for x in list(spreadsheet.df.nitecap_p.values)],
                        'filtered': spreadsheet.df.filtered_out.values.tolist()})
    return response


@spreadsheet_blueprint.route('/share', methods=['POST'])
@ajax_requires_login
def share(user=None):
    """
    AJAX endpoint - shares one of the user's spreadsheets.  Incoming json specifies the spreadsheet id and the cutoff
    to share.  Confirms that spreadsheet indeed belongs to the user and if so, returns a token which encrypts the
    spreadsheet id and cutoff.
    :param user:  Returned by the decorator.  Logged in user is required.
    :return: json {'share': <token>} unless the user's privileges are inadequate.
    """

    # Collect json data
    json_data = request.get_json()
    spreadsheet_id = json_data.get('spreadsheet_id', None)
    row_index = json_data.get('row_index', 0)

    # Bad data
    if not spreadsheet_id:
        return jsonify({"error": MISSING_SPREADSHEET_ID_ERROR}), 400

    # Attempt to access spreadsheet not owned.
    if not user.find_user_spreadsheet_by_id(spreadsheet_id):
        return jsonify({"errors": MANAGE_OWN_SPREADSHEETS_MESSAGE}, 401)

    current_app.logger.info(f"Sharing spreadsheet {spreadsheet_id} and row index {row_index}")
    return jsonify({'share': user.get_share_token(spreadsheet_id, row_index)})


@spreadsheet_blueprint.route('/share/<string:token>', methods=['GET'])
def consume_share(token):
    """
    Standard endpoint - obtains a shared spreadsheet.  The token is verified and the spreadsheet is
    checked against the sharing user's inventory to be sure that the spreadsheet still exists and is in fact, owned
    by the sharing user.  If either the sharing user does not exist or the spreadsheet to be shared does not exist in
    the sharing user's inventory, the receiving user is directed to the upload spreadsheet page and informed that the
    token was not comprehensible.  Otherwise a copy of all facets of the spreadsheet is made and assigned to the
    receiving user.  If the current user is not logged in, the user is assigned a visitor account.
    :param token: the share token given to the receiving user
    """
    errors = []
    sharing_user, spreadsheet_id, row_index = User.verify_share_token(token)
    current_app.logger.info(f"Consuming shared spreadsheet {spreadsheet_id}")
    spreadsheet = sharing_user.find_user_spreadsheet_by_id(spreadsheet_id)

    if not spreadsheet or not sharing_user:
        errors.append("The token you received does not work.  It may have been mangled in transit.  Please request"
                      "another share")
        return render_template('spreadsheets/spreadsheet_upload_form.html', errors=errors)

    # Identify the account of the current user.  If no account exists, create a visitor account.
    user = None
    if 'email' in session:
        user = User.find_by_email(session['email'])
    else:
        user = User.create_visitor()
        if user:
            # Visitor's session has a fixed expiry date.
            # session.permanent = True
            session['email'] = user.email
            session['visitor'] = user.is_visitor()

    # This should not happen ever - indicates a software bug
    if not user:
        errors.append("We are unable to create your share at the present time.  Please try again later")
        current_app.logger.error("Spreadsheet share consumption issue, unable to identify or generate a user.")
        return render_template('spreadsheets/spreadsheet_upload_form.html', errors=errors)

    # Create a copy of the sharing user's spreadsheet for the current user.
    shared_spreadsheet = Spreadsheet.make_share_copy(spreadsheet, user.id)
    if shared_spreadsheet:
        if row_index:
            shared_spreadsheet.breakpoint = row_index
            shared_spreadsheet.save_to_db()
        return redirect(url_for('spreadsheets.show_spreadsheet', spreadsheet_id=shared_spreadsheet.id))

    errors.append("The spreadsheet could not be shared.")
    return render_template('spreadsheets/spreadsheet_upload_form.html', errors=errors)


@spreadsheet_blueprint.route('/compare', methods=['GET'])
@requires_login
def compare(user=None):
    """
    Standard endpoint - compares two spreadsheets based upon the column ids they have in common.
    :param user: Returned by the decorator.  Logged in user is required.
    """

    errors = []

    spreadsheets = []
    non_unique_id_counts = []
    x_values = []
    x_labels = []
    x_label_values = []
    column_pairs = []
    columns = []
    datasets = []
    timepoints_per_day = []

    spreadsheet_ids = request.args.get('spreadsheet_ids', None)
    if not spreadsheet_ids or len(spreadsheet_ids.split(",")) != 2:
        errors.append("No spreadsheets were provided")
        return render_template('spreadsheets/user_spreadsheets.html', user=user, errors=errors)

    spreadsheet_ids = spreadsheet_ids.split(",")
    for spreadsheet_id in spreadsheet_ids:
        spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
        if not spreadsheet:
            return access_not_permitted(compare.__name__, user, spreadsheet_id)

        # Populate
        spreadsheet.init_on_load()

        spreadsheets.append(spreadsheet)
        
    errors = Spreadsheet.check_for_timepoint_consistency(spreadsheets)
    if errors:
        return render_template('spreadsheets/user_spreadsheets.html', user=user, errors=errors)

    descriptive_names = []
    for spreadsheet in spreadsheets:
        non_unique_ids = spreadsheet.find_replicate_ids()
        non_unique_id_counts.append(len(non_unique_ids))
        current_app.logger.debug(f"Number of non unique ids is {len(non_unique_ids)}")
        x_values.append(spreadsheet.x_values)
        x_labels.append(spreadsheet.x_labels)
        x_label_values.append(spreadsheet.x_label_values)
        column_pairs.append(spreadsheet.column_pairs)
        descriptive_names.append(spreadsheet.descriptive_name)
        timepoints_per_day.append(spreadsheet.timepoints)
        data = spreadsheet.df
        data["compare_ids"] = list(spreadsheet.get_ids())
        current_app.logger.debug(f"Shape prior to removal of non-unique ids: {data.shape}")
        data = data.set_index("compare_ids")
        data = data[~data.index.duplicated()]
        datasets.append(data)
        current_app.logger.debug(f"Shape prior to join with label col: {data.shape}")
    if not set(datasets[0].index) & set(datasets[1].index):
        errors.append("The spreadsheets have no IDs in common.  Perhaps the wrong column was selected as the ID?")
        return render_template('spreadsheets/user_spreadsheets.html', user=user, errors=errors)

    common_columns = set(datasets[0].columns).intersection(set(datasets[1].columns))
    df = datasets[0].join(datasets[1], how='inner', lsuffix='_0', rsuffix='_1')
    df = df.sort_values(by=['total_delta_0'])
    current_app.logger.debug(f"Shape after join: {df.shape}")
    compare_ids = df.index.tolist()
    datasets = []
    qs = []
    ps = []
    tds = []
    amplitudes = []
    peak_times = []
    anova_ps = []
    anova_qs = []
    for i in [0, 1]:
        columns.append([column + f"_{i}" if column in common_columns else column
                        for column in spreadsheets[i].get_data_columns()])
        datasets.append(df[columns[i]].values)
        qs.append(df[f"nitecap_q_{i}"].values.tolist())
        ps.append(df[f"nitecap_p_{i}"].values.tolist())
        amplitudes.append(df[f"amplitude_{i}"].values.tolist())
        peak_times.append(df[f"peak_time_{i}"].values.tolist())
        anova_ps.append(df[f"anova_p_{i}"].values.tolist())
        anova_qs.append(df[f"anova_q_{i}"].values.tolist())
        tds.append(df[f"total_delta_{i}"].tolist())

    return render_template('spreadsheets/comparison.html',
                           data=json.dumps([dataset.tolist() for dataset in datasets]),
                           x_values=x_values,
                           x_labels=x_labels,
                           x_label_values=x_label_values,
                           ids=compare_ids,
                           column_pairs=column_pairs,
                           descriptive_names=descriptive_names,
                           non_unique_id_counts=non_unique_id_counts,
                           qs=json.dumps(qs),
                           ps=json.dumps(ps),
                           amplitudes=json.dumps(amplitudes),
                           peak_times=json.dumps(peak_times),
                           anova_ps=json.dumps(anova_ps),
                           anova_qs=json.dumps(anova_qs),
                           tds=json.dumps(tds),
                           filtered=json.dumps(spreadsheets[0].df.filtered_out.tolist()),
                           timepoints_per_day=timepoints_per_day,
                           spreadsheet_ids=json.dumps(spreadsheet_ids))


@spreadsheet_blueprint.route('/get_upside', methods=['POST'])
@timeit
def get_upside():
    spreadsheet_ids = json.loads(request.data)['spreadsheet_ids']

    # Run Upside dampening analysis, if it hasn't already been stored to disk
    upside_ps = []
    upside_qs = []
    datasets = []
    spreadsheets = []

    # Check user ownership over these spreadsheets
    user = User.find_by_email(session['email'])
    for spreadsheet_id in spreadsheet_ids:
        spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
        if not spreadsheet:
            current_app.logger.warn(f"Attempted access for spreadsheet {spreadsheet_id} not owned by user {user.id}")
            return jsonify({'upside_ps': None})

        # Populate
        spreadsheet.init_on_load()

        spreadsheets.append(spreadsheet)

    for primary, secondary in [(0, 1), (1, 0)]:
        primary_id, secondary_id = spreadsheet_ids[primary], spreadsheet_ids[secondary]
        file_path = os.path.join(os.environ.get('UPLOAD_FOLDER'), f"{primary_id}v{secondary_id}.comparison.parquet")
        try:
            comp_data = pyarrow.parquet.read_pandas(file_path).to_pandas()
            upside_ps.append(comp_data["upside_ps"].values.tolist())
            upside_qs.append(comp_data["upside_qs"].values.tolist())
            current_app.logger.info(f"Loaded upside values from file {file_path}")
        except OSError: # Parquet file could not be read (hasn't been written yet)
            if not datasets:
                dfs = []
                for spreadsheet in spreadsheets:
                    data = spreadsheet.df
                    data["compare_ids"] = list(spreadsheet.get_ids())
                    data = data.set_index("compare_ids")
                    data = data[~data.index.duplicated()]
                    dfs.append(data)

                common_columns = set(dfs[0].columns).intersection(set(dfs[1].columns))
                df = dfs[0].join(dfs[1], how='inner', lsuffix='_0', rsuffix='_1')
                df = df.sort_values(by=['total_delta_0'])
                compare_ids = df.index.tolist()

                for i in [0, 1]:
                    columns = [column + f"_{i}" if column in common_columns else column
                                        for column in spreadsheets[i].get_data_columns()]
                    datasets.append(df[columns].values)

            # Run the actual upside calculation
            current_app.logger.info(f"Dataset sizes: {df.shape}, {datasets[primary].shape}, {datasets[secondary].shape}")
            upside_p = nitecap.upside.main(spreadsheets[primary].num_replicates, datasets[primary],
                                           spreadsheets[secondary].num_replicates, datasets[secondary])
            upside_q = nitecap.util.BH_FDR(upside_p)
            comp_data = pd.DataFrame(index=df.index)
            comp_data["upside_ps"] = upside_p
            comp_data["upside_qs"] = upside_q
            pyarrow.parquet.write_table(pyarrow.Table.from_pandas(comp_data), file_path)

            upside_ps.append(upside_p.tolist())
            upside_qs.append(upside_q.tolist())
            current_app.logger.info(f"Computed upside values and saved them to file {file_path}")

    return jsonify({
                'upside_ps': upside_ps,
                'upside_qs': upside_qs
            })


@spreadsheet_blueprint.route('/run_pca', methods=['POST'])
def run_pca():
    args = json.loads(request.data)
    spreadsheet_ids = args['spreadsheet_ids']
    selected_genes = args['selected_genes']
    take_zscore = args['take_zscore']
    take_log_transform = args['take_logtransform']

    # Run Upside dampening analysis, if it hasn't already been stored to disk
    datasets = []
    spreadsheets = []

    # Check user ownership over these spreadsheets
    user = User.find_by_email(session['email'])
    for spreadsheet_id in spreadsheet_ids:
        spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)

        # Populate
        spreadsheet.init_on_load()

        if not spreadsheet:
            current_app.logger.info("Attempted access for spreadsheet {spreadsheet_id} not owned by user")
            return jsonify({'upside_ps': None})
        spreadsheets.append(spreadsheet)

    dfs = []
    for spreadsheet in spreadsheets:
        data = spreadsheet.df
        data["compare_ids"] = list(spreadsheet.get_ids())
        data = data.set_index("compare_ids")
        data = data[~data.index.duplicated()]
        dfs.append(data)

    common_columns = set(dfs[0].columns).intersection(set(dfs[1].columns))
    df = dfs[0].join(dfs[1], how='inner', lsuffix='_0', rsuffix='_1')
    df = df.sort_values(by=['total_delta_0'])
    df = df.iloc[selected_genes]
    compare_ids = df.index.tolist()

    data_columns = [column + f"_{i}" if column in common_columns else column
                    for i in range(len(spreadsheets))
                    for column in spreadsheets[i].get_data_columns()]

    if take_log_transform:
        # log(1+x) transform data
        df[data_columns] = numpy.log(1 + df[data_columns])

    if take_zscore:
        # Normalize to z-scored data across both datasets
         df[data_columns] = (df[data_columns] - df[data_columns].mean(axis=0)) / df[data_columns].std(axis=0)

    # Extract individual datasets
    for i in [0, 1]:
        columns = [column + f"_{i}" if column in common_columns else column
                            for column in spreadsheets[i].get_data_columns()]
        datasets.append(df[columns].values)

    # Run the PCA
    pca = PCA(n_components=2)
    coords = pca.fit_transform(numpy.concatenate(datasets, axis=1).T)

    # Separate the coords into the two datasets
    pca_coords = []
    start = 0
    for dataset in datasets:
        num_cols = dataset.shape[1]
        pca_coords.append(coords[start:start + num_cols].T.tolist())
        start += num_cols
    return jsonify({
                'pca_coords': pca_coords,
                'explained_variance': pca.explained_variance_ratio_.tolist()
            })


@spreadsheet_blueprint.route('/check_id_uniqueness', methods=['POST'])
@requires_account
def check_id_uniqueness(user=None):
    """
    AJAX endpoint - determines whether the id columns selected by the user, in combination, form a unique identifier.
    Non unique identifier will be left out of comparisons.
    :param user:  Returned by the decorator.  Logged in user is required.
    :return: {'non-unique_ids': <non unique ids} or {'error': <error>}
    """

    errors = []

    json_data = request.get_json()
    spreadsheet_id = json_data.get('spreadsheet_id', None)
    id_columns = json_data.get('id_columns', None)

    if not id_columns:
        errors.append("No id columns were selected. Please select at least one id column.")
        return jsonify({'error': errors}), 400
    if not spreadsheet_id:
        return jsonify({'error': MISSING_SPREADSHEET_ID_ERROR}), 400
    else:
        spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
    if not spreadsheet:
        return jsonify({'error': MANAGE_OWN_SPREADSHEETS_MESSAGE}), 403

    # Populate
    spreadsheet.init_on_load()

    non_unique_ids = spreadsheet.find_replicate_ids(id_columns)
    current_app.logger.debug(f"Non-unique ids {non_unique_ids}")
    return jsonify({'non-unique_ids': non_unique_ids})


@spreadsheet_blueprint.route('/save_cutoff', methods=['POST'])
@ajax_requires_account
def save_cutoff(user=None):
    """
    AJAX endpoint - when the user selects a significance cutoff, in addition to showing the heatmap, the cutoff value
    is saved to the spreadsheet database record.
    :param user:  Returned by the decorator.  Account bearing user is required.
    :return: Nothing is returned in the event of a successful save.  Otherwise an error message is returned.
    """

    json_data = request.get_json()
    spreadsheet_id = json_data.get('spreadsheet_id', None)
    cutoff = json_data.get('cutoff', 0)

    # Spreadsheet id is required.
    if not spreadsheet_id:
        return jsonify({'error': MISSING_SPREADSHEET_ID_ERROR}), 400

    spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)

    if not spreadsheet:
        return jsonify({'error': MANAGE_OWN_SPREADSHEETS_MESSAGE}), 403

    spreadsheet.breakpoint = cutoff
    spreadsheet.save_to_db()
    return '', 204


@spreadsheet_blueprint.route('/save_note', methods=['POST'])
@ajax_requires_account
def save_note(user=None):
    """
    AJAX endpoint - accepts a json object { spreadsheet_id: spreadsheet id, note: note } and saves the contents
    of that note to the spreadsheet given by that spreadsheet id.  The spreadsheet id is checked to be sure
    that it represents a spreadsheet owned by this logged in user.  A successful save results in no content
    returned.  Otherwise an error is returned with the appropriate status code.
    :param user:  Returned by the decorator.  Account bearing user is required.
    :return: no content or { error: error } and a 400 or 404 code.
    """
    errors = []

    # Gather json data
    json_data = request.get_json()
    note = json_data.get('note', '')
    spreadsheet_id = json_data.get('spreadsheet_id', None)

    # Spreadsheet id is required.
    if not spreadsheet_id:
        return jsonify({'error': MISSING_SPREADSHEET_ID_ERROR}), 400

    spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
    if not spreadsheet:
        return jsonify({'error': MANAGE_OWN_SPREADSHEETS_MESSAGE}), 403

    spreadsheet.note = note
    spreadsheet.save_to_db()
    return '', 204


@spreadsheet_blueprint.route('/display_visitor_spreadsheets', methods=['GET'])
@requires_admin
def display_visitor_spreadsheets():
    """
    Standard endpoint - lists the spreadsheets belonging to visiting users.  Administrative function only.
    """
    users = User.find_visitors()
    return render_template('spreadsheets/display_visitor_spreadsheets.html', users=users)


@spreadsheet_blueprint.route('/delete_visitor_spreadsheets', methods=['POST'])
@ajax_requires_admin
def delete_visitor_spreadsheets():
    """
    AJAX endpoint - deletes the database table entry and the files associated with each of the
    spreadsheets whose ids are provided via a json object { spreadsheet_list: [spreadsheet ids].  That the
    spreadsheet belongs to a visiting user, is checked before removal and only those belonging to the visiting user
    are removed.  If removal is incomplete, the error is noted but removals of other spreadsheets continue.  If any
    problem occurred for any removal a 500 status code will be returned along with an error message.  Administrative
    function only.
    :return: json object - { errors: [error msgs] } with a status code of 500 if errors occurred and 200 otherwise.
    """
    errors = []
    spreadsheet_ids = json.loads(request.data).get('spreadsheet_list', None)
    for spreadsheet_id in spreadsheet_ids:
        spreadsheet = Spreadsheet.find_by_id(spreadsheet_id)
        if spreadsheet and spreadsheet.user.visitor:
            error = spreadsheet.delete()
            if error:
                errors.append(error)
    status_code = 500 if errors else 200
    return jsonify({'errors': errors}), status_code
