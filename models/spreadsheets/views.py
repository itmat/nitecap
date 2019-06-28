import json
import os
import pathlib
import shutil
import uuid
from pathlib import Path
import io
from string import Template

import magic
import numpy
import pandas as pd
import pyarrow
import pyarrow.parquet
from flask import Blueprint, request, session, url_for, redirect, render_template, send_file, flash, jsonify
from flask import current_app
import simplejson
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

MISSING_SPREADSHEET_MESSAGE = "No spreadsheet was provided."
SPREADSHEET_NOT_FOUND_MESSAGE = "No such spreadsheet could be found."
FILE_EXTENSION_ERROR = f"File must be one of the following types: {', '.join(constants.ALLOWED_EXTENSIONS)}"
FILE_UPLOAD_ERROR = "We are unable to load your spreadsheet at the present time.  Please try again later."

IMPROPER_ACCESS_TEMPLATE = Template('User $user_id attempted to apply the endpoint $endpoint to '
                                    'spreadsheet $spreadsheet_id.')


# Specialized JSON encoder for us that allows:
# A) the inclusion of pandas objects (anything with a to_json(orient='values') method)
# B) conversion of NaN and Inf to nulls
# While (B) is unfortunate it is necessary to get them it to parse in the browser on return from an ajax call
def json_encoder_for_pandas(obj):
    try:
        res = obj.to_json(orient="values")
    except:
        raise TypeError("Cannot serialize object")
    else:
        return simplejson.RawJSON(res)
json_encoder = simplejson.JSONEncoder(ignore_nan=True, default=json_encoder_for_pandas)
dumps = json_encoder.encode # Our encoder function

@spreadsheet_blueprint.route('/upload_file', methods=['GET', 'POST'])
@timeit
def upload_file():
    current_app.logger.info('Uploading spreadsheet')

    errors = []

    # Spreadsheet file form submitted
    if request.method == 'POST':
        header_row = request.form.get('header_row', None)
        if not header_row or not header_row.isdigit() or int(header_row) < 1:
            errors.append(f"The value of the header row is required and must be a positive integer.")
        upload_file = request.files.get('upload_file', None)
        if not upload_file or not len(upload_file.filename):
            errors.append(MISSING_SPREADSHEET_MESSAGE)
        if not allowed_file(upload_file.filename):
            errors.append(FILE_EXTENSION_ERROR)
        if errors:
            return render_template('spreadsheets/upload_file.html', header_row=header_row, errors=errors)

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
                session.permanent = True
                session['email'] = user.email
                session['visitor'] = True
                user_id = user.id

        # If we have no logged in user and a visitor account could not be generated, we have an internal
        # problem.
        if not user:
            current_app.logger.error("Spreadsheet load issue, unable to identify or generate a user.")
            return render_template('spreadsheets/upload_file.html', header_row=header_row,
                                   errors=[FILE_UPLOAD_ERROR])

        directory_path = pathlib.Path(os.path.join(os.environ.get('UPLOAD_FOLDER'),
                                                   f"user_{user_id}", f"{uuid.uuid4().hex}"))
        directory_path.mkdir(parents=True, exist_ok=True)

        # Rename the uploaded file and reattach the extension
        extension = Path(upload_file.filename).suffix
        file_path = os.path.join(directory_path, f"uploaded_spreadsheet{extension}")
        upload_file.save(file_path)

        # If the mime type validation fails, remove the directory containing the uploaded file from the disk
        file_mime_type, errors = validate_mime_type(file_path)
        if errors:
            shutil.rmtree(directory_path)
            return render_template('spreadsheets/upload_file.html', header_row=header_row ,errors=errors)

        # For some files masquerading as one of the acceptable file types by virtue of its file extension, we
        # may only be able to identify it as such when pandas fails to parse it while creating a spreadsheet object.
        # We throw the directory containing the file away and report the error.
        try:
            spreadsheet = Spreadsheet(descriptive_name=upload_file.filename,
                                      days=None,
                                      timepoints=None,
                                      repeated_measures=False,
                                      header_row=header_row,
                                      original_filename=upload_file.filename,
                                      file_mime_type=file_mime_type,
                                      uploaded_file_path=file_path,
                                      spreadsheet_data_path=str(directory_path),
                                      user_id=user_id)
        except NitecapException as ne:
            current_app.logger.error(f"NitecapException {ne}")
            shutil.rmtree(directory_path)
            return render_template('spreadsheets/upload_file.html', header_row=header_row, errors=[FILE_UPLOAD_ERROR])

        # Save the spreadsheet file to the database using the temporary spreadsheet data path (using the uuid)
        spreadsheet.save_to_db()

        # Recover the spreadsheet id and rename the spreadsheet directory accordingly.
        spreadsheet_data_path = os.path.join(user.get_user_directory_path(),
                                             spreadsheet.get_spreadsheet_data_directory_conventional_name())
        os.rename(directory_path, spreadsheet_data_path)

        # Update spreadsheet paths using the spreadsheet id and create the processed spreadsheet and finally, save the
        # updates.
        spreadsheet.spreadsheet_data_path = spreadsheet_data_path
        spreadsheet.uploaded_file_path = os.path.join(spreadsheet_data_path, os.path.basename(file_path))
        spreadsheet.setup_processed_spreadsheet()
        spreadsheet.save_to_db()

        return redirect(url_for('.collect_data', spreadsheet_id=spreadsheet.id))

    # Display spreadsheet file form
    return render_template('spreadsheets/upload_file.html')


@spreadsheet_blueprint.route('/collect_data/<spreadsheet_id>', methods=['GET', 'POST'])
@requires_account
def collect_data(spreadsheet_id, user=None):

    spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)

    # If the spreadsheet is not verified as owned by the user, the user is either returned to the his/her
    # spreadsheet list (in the case of a logged in user) or to the upload form (in the case of a visitor).
    if not spreadsheet:
        return access_not_permitted(collect_data.__name__, user, spreadsheet_id)

    # Set up the dataframe
    spreadsheet.set_df()

    # Spreadsheet data form submitted.
    if request.method == 'POST':
        descriptive_name, days, timepoints, repeated_measures, column_labels, errors = \
            validate_spreadsheet_data(request.form)

        if errors:
            return render_template('spreadsheets/collect_data.html', errors=errors, spreadsheet=spreadsheet)
        spreadsheet.descriptive_name = descriptive_name
        spreadsheet.days = int(days)
        spreadsheet.timepoints = int(timepoints)
        spreadsheet.repeated_measures = repeated_measures

        # If label assignments are improper, the user is returned to the column label form and invited to edit.
        errors = spreadsheet.validate(column_labels)
        if errors:
            return render_template('spreadsheets/collect_data.html', spreadsheet=spreadsheet, errors=errors)

        spreadsheet.identify_columns(column_labels)
        spreadsheet.set_ids_unique()
        spreadsheet.save_to_db()
        spreadsheet.init_on_load()
        spreadsheet.clear_jtk()
        spreadsheet.compute_nitecap()
        return redirect(url_for('.show_spreadsheet', spreadsheet_id=spreadsheet.id))
    return render_template('spreadsheets/collect_data.html', spreadsheet=spreadsheet)


@timeit
def validate_spreadsheet_data(form_data):
    """
    Helper method to collect form data and validate it
    :param form_data: the form dictionary from requests
    :return: a tuplbe consisting of the form data and an array of error msgs.  An empty array indicates no errors
    """

    # Gather data
    descriptive_name = form_data.get('descriptive_name', None)
    days = form_data.get('days', None)
    timepoints = form_data.get('timepoints', None)
    repeated_measures = form_data.get('repeated_measures', 'n')
    repeated_measures = True if repeated_measures == 'y' else False
    column_labels = [value for key, value in form_data.items() if key.startswith('col')]

    # Check data for errors
    errors = []
    if not descriptive_name or len(descriptive_name) > 250:
        errors.append(f"A descriptive name is required and may be no longer than 250 characters.")
    if not days or not days.isdigit():
        errors.append(f"The value for days is required and must be a positve integer.")
    if not timepoints or not timepoints.isdigit():
        errors.append(f"The value for timepoints is required and must be a positve integer.")
    return descriptive_name, days, timepoints, repeated_measures, column_labels, errors


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
    Helper method for situation where user attempts to access a spreadsheet that does not belong to him/her.  This
    could also be the case of a user attempting to access a spreadsheet that does not exist (e.g., a out of date
    bookmark).
    :param user: object of user attempting the access
    :param visitor: whether or not the user is a visitor (the page a visitor is dropped into is different from
    that of a logged in user
    :param spreadsheet_id: the id of the spreadsheet the user is attempting to access.
    :return: an appropriate page to which to return the user.
    """
    flash(SPREADSHEET_NOT_FOUND_MESSAGE)
    current_app.logger.warn(IMPROPER_ACCESS_TEMPLATE
                            .substitute(user_id=user.id, endpoint=endpoint, spreadsheet_id=spreadsheet_id))
    if user.is_visitor():
        return render_template(url_for('.upload_file'))
    return redirect(url_for('.display_spreadsheets'))


@spreadsheet_blueprint.route('/show_spreadsheet/<spreadsheet_id>', methods=['GET'])
@requires_account
@timeit
def show_spreadsheet(spreadsheet_id, user=None):
    """
    Standard endpoint - retrieves the spreadsheet id from the url and pulls up the associated display (graphics and tables).  This
    method is available to any user with an account (standard user or visitor).
    :param spreadsheet_id: the id of the spreadsheet whose results are to be displayed.
    :param user:  Returned by the decorator.  Account bearing user is required.
    """

    errors = []

    spreadsheets = []

    try:
        spreadsheet_ids = [int(ID) for ID in spreadsheet_id.split(',')]
    except ValueError:
        errors.append("Unknown spreadsheet id(s)")
        return render_template('spreadsheets/user_spreadsheets.html', user=user, errors=errors)

    if not spreadsheet_ids:
        errors.append("No spreadsheets were provided")
        return render_template('spreadsheets/user_spreadsheets.html', user=user, errors=errors)

    for spreadsheet_id in spreadsheet_ids:
        spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
        if not spreadsheet:
            return access_not_permitted(compare.__name__, user, spreadsheet_id)

        # Populate
        spreadsheet.init_on_load()

        spreadsheets.append(spreadsheet)

    #errors = Spreadsheet.check_for_timepoint_consistency(spreadsheets)
    #if errors:
    #    return render_template('spreadsheets/user_spreadsheets.html', user=user, errors=errors)

    return render_template('spreadsheets/comparison.html',
                           spreadsheet_ids=[int(ID) for ID in spreadsheet_ids],
                           descriptive_names=[spreadsheet.descriptive_name for spreadsheet in spreadsheets])


@spreadsheet_blueprint.route('/get_spreadsheets', methods=['POST'])
@timeit
@ajax_requires_account
def get_spreadsheets(user=None):

    spreadsheet_ids = json.loads(request.data)['spreadsheet_ids']

    if not spreadsheet_ids:
        return jsonify({"error": MISSING_SPREADSHEET_MESSAGE}), 400

    spreadsheets = []
    for spreadsheet_id in spreadsheet_ids:
        spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
        if not spreadsheet:
            return access_not_permitted(compare.__name__, user, spreadsheet_id)

        # Populate
        spreadsheet.init_on_load()

        spreadsheets.append(spreadsheet)

    dfs, combined_index = Spreadsheet.join_spreadsheets(spreadsheets)

    # TODO: should load JTK ps and qs here if available, currently just report them as None

    # Gather all values except for the actual numerical data
    # Which is handled separately
    spreadsheet_values = []
    for spreadsheet, df in zip(spreadsheets, dfs):
        values = dict(
                     data=df[spreadsheet.get_data_columns()],
                     x_values=spreadsheet.x_values,
                     x_labels=spreadsheet.x_labels,
                     x_label_values=spreadsheet.x_label_values,
                     qs=df.nitecap_q,
                     ps=df.nitecap_p,
                     tds=df.total_delta,
                     amplitudes=df.amplitude,
                     peak_times=df.peak_time,
                     anova_ps=df.anova_p,
                     anova_qs=df.anova_q,
                     filtered=df.filtered_out,
                     filters=spreadsheet.filters if spreadsheet.filters else [],
                     labels=combined_index.to_list(),
                     breakpoint=spreadsheet.breakpoint if spreadsheet.breakpoint is not None else 0,
                     descriptive_name=spreadsheet.descriptive_name,
                     timepoints_per_day=spreadsheet.timepoints,
                     spreadsheet_id=spreadsheet.id,
                     spreadsheet_note=spreadsheet.note,
                     visitor=user.is_visitor(),
                     column_headers=spreadsheet.get_data_columns(),
                     jtk_ps=None,
                     jtk_qs=None,
                    )
        spreadsheet_values.append(values)

    return dumps(spreadsheet_values)

@spreadsheet_blueprint.route('/jtk', methods=['POST'])
@timeit
@ajax_requires_account
def get_jtk(user=None):

    spreadsheet_ids = json.loads(request.data)['spreadsheet_ids']

    if not spreadsheet_ids:
        return jsonify({"error": MISSING_SPREADSHEET_MESSAGE}), 400

    spreadsheets = []
    for spreadsheet_id in spreadsheet_ids:
        spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
        if not spreadsheet:
            return access_not_permitted(compare.__name__, user, spreadsheet_id)

        # Populate
        spreadsheet.init_on_load()

        spreadsheets.append(spreadsheet)

    # Running it once will calculate JTK if necessary
    [spreadsheet.get_jtk() for spreadsheet in spreadsheets]

    # Inner join of the spreadsheets so that they match indexes
    dfs, combined_index = Spreadsheet.join_spreadsheets(spreadsheets)

    # Now just extract the right columns
    jtk_ps = [df["jtk_p"] for df in dfs]
    jtk_qs = [df["jtk_q"] for df in dfs]

    return dumps({"jtk_ps": jtk_ps, "jtk_qs": jtk_qs})


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
        return jsonify({"error": MISSING_SPREADSHEET_MESSAGE}), 400

    spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
    if not spreadsheet:
        current_app.logger.warn(IMPROPER_ACCESS_TEMPLATE
                                .substitute(user_id=user.id, endpoint=request.path, spreadsheet_id=spreadsheet_id))
        return jsonify({"error": SPREADSHEET_NOT_FOUND_MESSAGE}), 404

    try:
        spreadsheet.delete_from_db()
        shutil.rmtree(spreadsheet.spreadsheet_data_path)
    except Exception as e:
        current_app.logger.error(f"The data for spreadsheet {spreadsheet_id} could not all be successfully "
                                 f"expunged.", e)
        return jsonify({"error": 'The spreadsheet data may not have been all successfully removed'}), 500
    return '', 204


@spreadsheet_blueprint.route('/download_comparison/<int:id1>,<int:id2>', methods=['GET'])
@requires_account
def download_comparison(id1, id2, user=None):
    """
    Response to a request from the graphs page to download the spreadsheet whose id is in the session.  In this case,
    the user need not be logged in.  Nevertheless, the requested spreadsheet must be in the user's inventory.  In the
    case of a visitor, the spreadsheet must not be in the inventory of any logged in user.  If the user is authorized
    to download the spreadsheet and the file is available, the file representing the fully processed version of the
    spreadsheet is delivered as an attachment.
    :param user:  Returned by the decorator.  Account bearing user is required.
    """

    comparisons_directory = os.path.join(user.get_user_directory_path(), "comparisons")
    spreadsheet_ids = [id1, id2]

    if not spreadsheet_ids:
        return jsonify({"error": MISSING_SPREADSHEET_MESSAGE}), 400

    spreadsheets = []
    for spreadsheet_id in spreadsheet_ids:
        spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
        if not spreadsheet:
            return access_not_permitted(compare.__name__, user, spreadsheet_id)

    #    Not currently being used.
    #    # Populate
    #    spreadsheet.init_on_load()

        spreadsheets.append(spreadsheet)

    #dfs, combined_index = Spreadsheet.join_spreadsheets(spreadsheets)

    comparison_data = []
    for primary, secondary in [(0, 1), (1, 0)]:
        primary_id, secondary_id = spreadsheet_ids[primary], spreadsheet_ids[secondary]
        file_path = os.path.join(comparisons_directory, f"{primary_id}v{secondary_id}.comparison.parquet")
        try:
            comp_data = pyarrow.parquet.read_pandas(file_path).to_pandas()
            current_app.logger.info(f"Loaded upside values from file {file_path}")
            comparison_data.append(comp_data)
        except OSError: # Parquet file could not be read (hasn't been written yet)
            current_app.logger.info(f"Failed to download comparison spreadsheet since we can't load the file {primary_id}v{secondary_id}.comparison.parquet")
            return jsonify("Computations not finished yet"), 500

    # TODO: what exactly should be in this dataset?
    # Right now it's JUST the comparison data and not the base data from either spreadsheet
    df = comparison_data[0].join(comparison_data[1], lsuffix="_AvB", rsuffix="_BvA")

    txt_data = io.StringIO()
    df.to_csv(txt_data, sep='\t')
    txt = txt_data.getvalue()
    byte_data = io.BytesIO(str.encode(txt))

    return send_file(byte_data, mimetype="text/plain", as_attachment=True, attachment_filename='processed_spreadsheet.txt')

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
            return access_not_permitted(request.path, user, spreadsheet_id)
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
        return render_template('spreadsheets/upload_file.html', errors=errors)


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
    spreadsheet_id = json_data.get('spreadsheet_id', None)
    filtered_out = json_data.get('filtered_out', None)
    rerun_qvalues = json_data.get('rerun_qvalues', False)
    filters = json_data.get('filters', '[]')

    # Bad data
    if not spreadsheet_id:
        return jsonify({"error": MISSING_SPREADSHEET_MESSAGE}), 400

    # Collect spreadsheet owned by user
    spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)

    # Attempt to access spreadsheet not owned.
    if not spreadsheet:
        current_app.logger.warn(IMPROPER_ACCESS_TEMPLATE
                                .substitute(user_id=user.id, endpoint=request.path, spreadsheet_id=spreadsheet_id))
        return jsonify({"error": SPREADSHEET_NOT_FOUND_MESSAGE}), 404

    # Check request data
    if not filtered_out:
        return jsonify({"error": "Incomplete request data, need 'filtered_out'"}), 400

    # Verify that the filters are valid JSON
    try:
        _ = json.loads(filters)
    except json.JSONDecodeError:
        return jsonify({"error": "Error parsing 'filters' json blob"}), 400

    # Populate spreadsheet with raw data
    spreadsheet.init_on_load()

    spreadsheet.filters = filters
    spreadsheet.apply_filters(filtered_out, rerun_qvalues)
    spreadsheet.save_to_db()

    response = jsonify({'qs': [x if x == x else None for x in list(spreadsheet.df.nitecap_q.values)],
                        'ps': [x if x == x else None for x in list(spreadsheet.df.nitecap_p.values)],
                        'jtk_qs': [x if x == x else None for x in list(spreadsheet.df.jtk_q.values)],
                        'anova_qs': [x if x == x else None for x in list(spreadsheet.df.anova_q.values)]})
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
        return jsonify({"error": MISSING_SPREADSHEET_MESSAGE}), 400

    # Attempt to access spreadsheet not owned.
    if not user.find_user_spreadsheet_by_id(spreadsheet_id):
        current_app.logger.warn(IMPROPER_ACCESS_TEMPLATE.substitute(user.id, request.path, spreadsheet_id))
        return jsonify({"errors": SPREADSHEET_NOT_FOUND_MESSAGE}, 404)

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
        return render_template('spreadsheets/upload_file.html', errors=errors)

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
        return render_template('spreadsheets/upload_file.html', errors=errors)

    # Create a copy of the sharing user's spreadsheet for the current user.nitecap
    shared_spreadsheet = Spreadsheet.make_share_copy(spreadsheet, user.id)
    if shared_spreadsheet:
        if row_index:
            shared_spreadsheet.breakpoint = row_index
            shared_spreadsheet.save_to_db()
        return redirect(url_for('spreadsheets.show_spreadsheet', spreadsheet_id=shared_spreadsheet.id))

    errors.append("The spreadsheet could not be shared.")
    return render_template('spreadsheets/upload_file.html', errors=errors)


@spreadsheet_blueprint.route('/compare', methods=['GET'])
@requires_login
def compare(user=None):
    """
    Standard endpoint - compares two spreadsheets based upon the column ids they have in common.
    :param user: Returned by the decorator.  Logged in user is required.
    """

    errors = []

    spreadsheets = []

    spreadsheet_ids = request.args.get('spreadsheet_ids', None)
    if not spreadsheet_ids: # or len(spreadsheet_ids.split(",")) != 2:
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

    #errors = Spreadsheet.check_for_timepoint_consistency(spreadsheets)
    #if errors:
    #    return render_template('spreadsheets/user_spreadsheets.html', user=user, errors=errors)

    return render_template('spreadsheets/comparison.html',
                           spreadsheet_ids=[int(ID) for ID in spreadsheet_ids],
                           descriptive_names=[spreadsheet.descriptive_name for spreadsheet in spreadsheets])


@spreadsheet_blueprint.route('/get_upside', methods=['POST'])
@timeit
@ajax_requires_login
def get_upside(user=None):
    comparisons_directory = os.path.join(user.get_user_directory_path(), "comparisons")
    if not os.path.exists(comparisons_directory):
        os.makedirs(comparisons_directory, exist_ok=True)

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

        spreadsheets.append(spreadsheet)

    anova_p = None
    anova_q = None
    for primary, secondary in [(0, 1), (1, 0)]:
        primary_id, secondary_id = spreadsheet_ids[primary], spreadsheet_ids[secondary]
        file_path = os.path.join(comparisons_directory, f"{primary_id}v{secondary_id}.comparison.parquet")
        try:
            comp_data = pyarrow.parquet.read_pandas(file_path).to_pandas()
            upside_ps.append(comp_data["upside_ps"].values.tolist())
            upside_qs.append(comp_data["upside_qs"].values.tolist())
            anova_p = comp_data["two_way_anova_ps"]
            anova_q = comp_data["two_way_anova_qs"]
            phase_p = comp_data["phase_ps"]
            phase_q = comp_data["phase_qs"]
            amplitude_p = comp_data["amplitude_ps"]
            amplitude_q = comp_data["amplitude_qs"]
            current_app.logger.info(f"Loaded upside values from file {file_path}")
        except OSError: # Parquet file could not be read (hasn't been written yet)
            if not datasets:
                # Populate all
                for spreadsheet in spreadsheets:
                    spreadsheet.init_on_load()

                dfs, combined_index = Spreadsheet.join_spreadsheets(spreadsheets)

                datasets = [df[spreadsheet.get_data_columns()].values for df, spreadsheet in zip(dfs, spreadsheets)]

            # Run the actual upside calculation
            upside_p = nitecap.upside.main(spreadsheets[primary].num_replicates_by_time, datasets[primary],
                                           spreadsheets[secondary].num_replicates_by_time, datasets[secondary])
            upside_q = nitecap.util.BH_FDR(upside_p)

            if anova_p is None:
                # Run two-way anova
                anova_p = nitecap.util.two_way_anova(spreadsheets[primary].num_replicates_by_time, datasets[primary],
                                                     spreadsheets[secondary].num_replicates_by_time, datasets[secondary])
                anova_q = nitecap.util.BH_FDR(anova_p)

                # Run Cosinor analysis
                amplitude_p, phase_p = nitecap.util.cosinor_analysis(spreadsheets[primary].num_replicates_by_time, datasets[primary],
                                                                     spreadsheets[secondary].num_replicates_by_time, datasets[secondary])
                phase_q = nitecap.util.BH_FDR(phase_p)
                amplitude_q = nitecap.util.BH_FDR(amplitude_p)

            comp_data = pd.DataFrame(index=combined_index)
            comp_data["upside_ps"] = upside_p
            comp_data["upside_qs"] = upside_q
            comp_data["two_way_anova_ps"] = anova_p
            comp_data["two_way_anova_qs"] = anova_q
            comp_data["phase_ps"] = phase_p
            comp_data["phase_qs"] = phase_q
            comp_data["amplitude_ps"] = amplitude_p
            comp_data["amplitude_qs"] = amplitude_q

            # Save to disk
            pyarrow.parquet.write_table(pyarrow.Table.from_pandas(comp_data), file_path)

            upside_ps.append(upside_p.tolist())
            upside_qs.append(upside_q.tolist())
            current_app.logger.info(f"Computed upside values and saved them to file {file_path}")

    return dumps({
                'upside_ps': upside_ps,
                'upside_qs': upside_qs,
                'two_way_anova_ps': anova_p.tolist(),
                'two_way_anova_qs': anova_q.tolist(),
                'phase_ps': phase_p.tolist(),
                'phase_qs': phase_q.tolist(),
                'amplitude_ps': amplitude_p.tolist(),
                'amplitude_qs': amplitude_q.tolist()
            })


@spreadsheet_blueprint.route('/run_pca', methods=['POST'])
@ajax_requires_account
def run_pca(user=None):
    args = json.loads(request.data)
    spreadsheet_ids = args['spreadsheet_ids']
    selected_genes = args['selected_genes']
    take_zscore = args['take_zscore']
    take_log_transform = args['take_logtransform']

    if not spreadsheet_ids:
        return jsonify({"error": MISSING_SPREADSHEET_MESSAGE}), 400

    spreadsheets = []
    for spreadsheet_id in spreadsheet_ids:
        spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
        if not spreadsheet:
            return access_not_permitted(compare.__name__, user, spreadsheet_id)

        # Populate
        spreadsheet.init_on_load()

        spreadsheets.append(spreadsheet)

    # Inner join of the spreadsheets so that they match indexes
    dfs, combined_index = Spreadsheet.join_spreadsheets(spreadsheets)

    datasets = [df.iloc[selected_genes][spreadsheet.get_data_columns()].values for df,spreadsheet in zip(dfs, spreadsheets)]

    data = numpy.concatenate(datasets, axis=1)

    # Drop rows that contain NaNs
    data = data[numpy.isfinite(data).all(axis=1)]
    if data.shape[0] < 3:
        return "Insufficient non-NaN rows selected. Need at least 3", 500

    if take_log_transform:
        # log(1+x) transform data
        data = numpy.log(1 + data)

    if take_zscore:
        # Normalize to z-scored data across both datasets
         data = (data - data.mean(axis=0)) / data.std(axis=0)

    # Run the PCA
    pca = PCA(n_components=2)
    try:
        coords = pca.fit_transform(data.T)
    except ValueError:
        return "NaN value encountered - PCA must be run on only non-NaN, non-empty values", 500

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
    AJAX endpoint - accepts a json object ( id_columns: id_columns, spreadsheet_id: spreadsheet_id } and determines
    whether the id columns selected by the user, in combination, form a unique identifier.  Non unique ids will be left
    out of comparisons.  The spreadsheet id is checked to be sure that it represents a spreadsheet owned by this user
    account.  A successful save results in a list of non unique ids returned, if any.  Otherwise an error is returned
    with the appropriate status code.
    :param user:  Returned by the decorator.   Account bearing user is required.
    :return: { non-unique_ids: non unique ids } or { error: error } and a 400 or 404 code.
    """

    errors = []

    json_data = request.get_json()
    spreadsheet_id = json_data.get('spreadsheet_id', None)
    id_columns = json_data.get('id_columns', None)

    if not id_columns:
        errors.append("No id columns were selected. Please select at least one id column.")
        return jsonify({'error': errors}), 400
    if not spreadsheet_id:
        return jsonify({'error': MISSING_SPREADSHEET_MESSAGE}), 400
    else:
        spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
    if not spreadsheet:
        current_app.logger.warn(IMPROPER_ACCESS_TEMPLATE
                                .substitute(user_id=user.id, endpoint=request.path, spreadsheet_id=spreadsheet_id))
        return jsonify({'error': SPREADSHEET_NOT_FOUND_MESSAGE}), 404

    # Populate
    spreadsheet.set_df()

    non_unique_ids = spreadsheet.find_replicate_ids(id_columns)
    current_app.logger.debug(f"Non-unique ids {non_unique_ids}")
    return jsonify({'non-unique_ids': non_unique_ids})


@spreadsheet_blueprint.route('/save_cutoff', methods=['POST'])
@ajax_requires_account
def save_cutoff(user=None):
    """
    AJAX endpoint - accepts a json object ( spreadsheet_id: spreadsheet_id, cutoff: cutoff value } and saves the
    significance cutoff value to the spreadsheet given by that spreadsheet id.  The spreadsheet id is checked to be
    sure that it represents a spreadsheet owned by this user account.  A successful save results in no content
    returned.  Otherwise an error is returned with the appropriate status code.
    :param user:  Returned by the decorator.  Account bearing user is required.
    :return: no content (204) or { error: error } and a 400 or 404 code.
    """

    json_data = request.get_json()
    spreadsheet_id = json_data.get('spreadsheet_id', None)
    cutoff = json_data.get('cutoff', 0)

    # Spreadsheet id is required.
    if not spreadsheet_id:
        return jsonify({'error': [MISSING_SPREADSHEET_MESSAGE]}), 400

    spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)

    if not spreadsheet:
        current_app.logger.warn(IMPROPER_ACCESS_TEMPLATE
                                .substitute(user_id=user.id, endpoint=request.path, spreadsheet_id=spreadsheet_id))
        return jsonify({'error': SPREADSHEET_NOT_FOUND_MESSAGE}), 404

    spreadsheet.breakpoint = cutoff
    spreadsheet.save_to_db()
    return '', 204


@spreadsheet_blueprint.route('/save_note', methods=['POST'])
@ajax_requires_account
def save_note(user=None):
    """
    AJAX endpoint - accepts a json object { spreadsheet_id: spreadsheet id, note: note } and saves the contents
    of that note to the spreadsheet given by that spreadsheet id.  The spreadsheet id is checked to be sure
    that it represents a spreadsheet owned by this user account.  A successful save results in no content
    returned.  Otherwise an error is returned with the appropriate status code.
    :param user:  Returned by the decorator.  Account bearing user is required.
    :return: no content (204) or { error: error } and a 400 or 404 code.
    """

    # Gather json data
    json_data = request.get_json()
    note = json_data.get('note', '')
    spreadsheet_id = json_data.get('spreadsheet_id', None)

    # Spreadsheet id is required.
    if not spreadsheet_id:
        return jsonify({'error': MISSING_SPREADSHEET_MESSAGE}), 400

    spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
    if not spreadsheet:
        current_app.logger.warn(IMPROPER_ACCESS_TEMPLATE
                                .substitute(user_id=user.id, endpoint=request.path, spreadsheet_id=spreadsheet_id))
        return jsonify({'error': SPREADSHEET_NOT_FOUND_MESSAGE}), 404

    spreadsheet.note = note
    spreadsheet.save_to_db()
    return '', 204

@spreadsheet_blueprint.route('/rename', methods=['POST'])
@ajax_requires_account
def rename(user=None):
    """
    AJAX endpoint - accepts a json object {spreadsheet_id: spreadsheet id, name: name } and saves the new name (if
    one is provided) to the spreadsheet given by that spreadsheet id.  The spreadsheet id is checked to be sure
    that it represents a spreadsheet owned by this user account.  A successful save results in a json object containing
    the current descriptive name {name: spreadsheet.descriptive_name } being returned.  Otherwise an error is returned
    with the appropriate status code.
    :param user: Returned by the decorator.  Account bearing user is required.
    :return: {name: descriptive_name} or { error: error } and a 400 or 404 code.
    """

    # Gather json data
    json_data = request.get_json()
    name = json_data.get('name', None)
    spreadsheet_id = json_data.get('spreadsheet_id', None)

    # Spreadsheet id is required.
    if not spreadsheet_id:
        return jsonify({'error': MISSING_SPREADSHEET_MESSAGE}), 400

    spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
    if not spreadsheet:
        current_app.logger.warn(IMPROPER_ACCESS_TEMPLATE
                                .substitute(user_id=user.id, endpoint=request.path, spreadsheet_id=spreadsheet_id))
        return jsonify({'error': SPREADSHEET_NOT_FOUND_MESSAGE}), 404

    # If no name was provided, do not alter the existing descriptive name
    if name:
        spreadsheet.descriptive_name = name
        spreadsheet.save_to_db()
    return jsonify({'name': spreadsheet.descriptive_name})

@spreadsheet_blueprint.route('/bulk_delete', methods=['POST'])
@requires_login
def bulk_delete(user=None):
    """
    AJAX endpoint - deletes the database table entry and the files associated with each of the
    spreadsheets whose ids are provided via a json object { spreadsheet_ids: [spreadsheet ids] }. The spreadsheet id
    is checked to be sure that it represents a spreadsheet owned by this user account.
    :param user: Returned by the decorator.  Account bearing user is required.
    :return: { spreadsheet_removed_ids: [spreadsheet_removed_ids], errors: [errors] } returned with an array of errors
     a and status code of 200 regardless.  The only difference between the input list of spreadsheet ids and the output
     list of id removed is the possibly that one or more spreadsheet ids represents spreadsheet not belonging to the
     user.  Those will not appear in the list of ids removed.
    """

    errors = []
    spreadsheet_removed_ids = []
    spreadsheet_ids = json.loads(request.data).get('spreadsheet_ids', None)
    for spreadsheet_id in spreadsheet_ids:
        spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
        if not spreadsheet:
            current_app.logger.warn(IMPROPER_ACCESS_TEMPLATE
                                    .substitute(user_id=user.id, endpoint=request.path, spreadsheet_id=spreadsheet_id))
            errors.append(SPREADSHEET_NOT_FOUND_MESSAGE)
            continue
        error = spreadsheet.delete()
        if error:
            errors.append(error)
        spreadsheet_removed_ids.append(spreadsheet_id)
    return jsonify({'spreadsheet_removed_ids': spreadsheet_removed_ids, 'errors': errors})


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
