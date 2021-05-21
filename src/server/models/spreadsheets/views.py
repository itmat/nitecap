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
from itsdangerous import JSONWebSignatureSerializer as Serializer

import constants
import nitecap
from exceptions import NitecapException
from models.spreadsheets.spreadsheet import Spreadsheet, NITECAP_DATA_COLUMNS
from models.users.decorators import requires_login, requires_admin, requires_account, ajax_requires_login, \
    ajax_requires_account, ajax_requires_account_or_share, ajax_requires_admin
from models.users.user import User
from models.shares import Share
from models.jobs import Job
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
    errors = []

    # Spreadsheet file form submitted
    if request.method == 'POST':
        header_row = request.form.get('header_row', None)
        if not header_row or not header_row.isdigit() or int(header_row) < 1:
            errors.append(f"The value of the header row is required and must be a positive integer.")
        upload_file = request.files.get('upload_file', None)
        if not upload_file or not len(upload_file.filename):
            errors.append(MISSING_SPREADSHEET_MESSAGE)
        elif not allowed_file(upload_file.filename):
            errors.append(FILE_EXTENSION_ERROR)
        if errors:
            return jsonify({"errors": errors}), 400
            #return render_template('spreadsheets/upload_file.html', header_row=header_row, errors=errors)

        # Identify any logged in user or current visitor accout so that ownership of the spreadsheet is established.
        user_id = None
        user_email = session['email'] if 'email' in session else None
        if user_email:
            user = User.find_by_email(user_email)
            user_id = user.id if user else None

            current_app.logger.info(f'Uploading spreadsheet for user {user_email}')

        # If user is not logged in or has a current visitor accout, assign a visitor account to protect user's
        # spreadsheet ownership.
        else:
            user = User.create_visitor()
            current_app.logger.info("Uploading spreadsheet from new visitor")
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
            return jsonify({"errors": [FILE_UPLOAD_ERROR]}), 500

        directory_path = pathlib.Path(os.path.join(user.get_user_directory_path(), f"{uuid.uuid4().hex}"))
        directory_path.mkdir(parents=True, exist_ok=True)

        # Rename the uploaded file and reattach the extension
        extension = Path(upload_file.filename).suffix
        file_path = os.path.join(directory_path, f"uploaded_spreadsheet{extension}")
        upload_file.save(file_path)

        # If the mime type validation fails, remove the directory containing the uploaded file from the disk
        file_mime_type, errors = validate_mime_type(file_path)
        if errors:
            shutil.rmtree(directory_path)
            return jsonify({"errors": errors}), 400

        # For some files masquerading as one of the acceptable file types by virtue of its file extension, we
        # may only be able to identify it as such when pandas fails to parse it while creating a spreadsheet object.
        # We throw the directory containing the file away and report the error.
        try:
            spreadsheet = Spreadsheet(descriptive_name=upload_file.filename,
                                      days=None,
                                      timepoints=None,
                                      num_timepoints=None,
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
            return jsonify({"errors": [FILE_UPLOAD_ERROR]}), 400

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

        return jsonify({"url": url_for('.collect_data', spreadsheet_id=spreadsheet.id)})

    # Display spreadsheet file form
    return render_template('spreadsheets/upload_file.html')


from computation.api import store_spreadsheet_to_s3


@spreadsheet_blueprint.route('/collect_data/<spreadsheet_id>', methods=['GET', 'POST'])
@requires_account
def collect_data(spreadsheet_id, user=None):

    current_app.logger.info(f"Collecting spreadsheet data from spreadsheet {spreadsheet_id}, user {user.email}")
    spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)

    # If the spreadsheet is not verified as owned by the user, the user is either returned to the his/her
    # spreadsheet list (in the case of a logged in user) or to the upload form (in the case of a visitor).
    if not spreadsheet:
        return access_not_permitted(collect_data.__name__, user, spreadsheet_id)

    # Spreadsheet data form submitted.
    if request.method == 'POST':
        descriptive_name, num_timepoints, timepoints, repeated_measures, column_labels, errors = \
            validate_spreadsheet_data(request.form)

        if errors:
            return render_template('spreadsheets/collect_data.html', errors=errors, spreadsheet=spreadsheet)
        spreadsheet.descriptive_name = descriptive_name
        spreadsheet.num_timepoints = int(num_timepoints)
        spreadsheet.timepoints = int(timepoints)
        spreadsheet.repeated_measures = repeated_measures

        # Load the DF to do the initial assessment
        spreadsheet.init_on_load()

        # If label assignments are improper, the user is returned to the column label form and invited to edit.
        errors = spreadsheet.validate(column_labels)
        if errors:
            return render_template('spreadsheets/collect_data.html', spreadsheet=spreadsheet, errors=errors)

        spreadsheet.identify_columns(column_labels)

        # Check for any comparisons already computed and delete those for recomputation
        comparisons_directory = pathlib.Path(os.path.join(user.get_user_directory_path(), "comparisons"))
        if comparisons_directory.exists():
            for path in comparisons_directory.glob(f"*v{spreadsheet.id}.comparison.parquet"):
                path.unlink()
            for path in comparisons_directory.glob(f"{spreadsheet.id}v*.comparison.parquet"):
                path.unlink()


        # Trigger recomputations as necessary
        spreadsheet.set_ids_unique()
        spreadsheet.increment_edit_version()
        spreadsheet.compute_nitecap()
        spreadsheet.save_to_db()
        store_spreadsheet_to_s3(spreadsheet)
        return redirect(url_for('.show_spreadsheet', spreadsheet_id=spreadsheet.id))

    spreadsheet.init_on_load()
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
    num_timepoints = form_data.get('num_timepoints', None)
    timepoints = form_data.get('timepoints', None)
    repeated_measures = form_data.get('repeated_measures', 'n')
    repeated_measures = True if repeated_measures == 'y' else False
    column_labels = [value for key, value in form_data.items() if key.startswith('col')]

    # Check data for errors
    errors = []
    if not descriptive_name or len(descriptive_name) > 250:
        errors.append(f"A descriptive name is required and may be no longer than 250 characters.")
    if not timepoints or not timepoints.isdigit() or not int(timepoints) > 0:
        errors.append(f"The number of timepoints per cycle must be a positve integer.")
    if not num_timepoints or not num_timepoints.isdigit() or not (int(num_timepoints) >= int(num_timepoints)):
        errors.append(f"The number of timepoints must be an integer greater than or equal to the timepoints per cycle.")
    return descriptive_name, num_timepoints, timepoints, repeated_measures, column_labels, errors


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
    that of a logged in user)
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
def show_spreadsheet(spreadsheet_id, user=None, config=None):
    """
    Standard endpoint - retrieves the spreadsheet id from the url and pulls up the associated display (graphics and tables).  This
    method is available to any user with an account (standard user or visitor).
    :param spreadsheet_id: the id of the spreadsheet whose results are to be displayed.
    :param user:  Returned by the decorator.  Account bearing user is required.
    """

    if config is None:
        config = dict()

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

    current_app.logger.info(f"Showing spreadsheet(s) {spreadsheet_ids} from user {user.email}")

    for spreadsheet_id in spreadsheet_ids:
        spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
        if not spreadsheet:
            return access_not_permitted(show_spreadsheet.__name__, user, spreadsheet_id)
        spreadsheets.append(spreadsheet)

    is_categorical = [spreadsheet.is_categorical() for spreadsheet in spreadsheets]
    if any(is_categorical) and not all(is_categorical):
        flash("Spreadsheets must all be categorical or all time-series.")
        return redirect(url_for('.display_spreadsheets'))

    #errors = Spreadsheet.check_for_timepoint_consistency(spreadsheets)
    #if errors:
    #    return render_template('spreadsheets/user_spreadsheets.html', user=user, errors=errors)

    if all(is_categorical):
        return render_template('spreadsheets/show_mpv_spreadsheet.html',
                           spreadsheet_ids=spreadsheet_ids,
                           config=config,
                           user_id=user.id,
                           NOTIFICATION_API_ENDPOINT=os.environ['NOTIFICATION_API_ENDPOINT'],
                           descriptive_names=[spreadsheet.descriptive_name for spreadsheet in spreadsheets])
    else:
        return render_template('spreadsheets/comparison.html',
                           spreadsheet_ids=spreadsheet_ids,
                           config=config,
                           user_id=user.id,
                           NOTIFICATION_API_ENDPOINT=os.environ['NOTIFICATION_API_ENDPOINT'],
                           descriptive_names=[spreadsheet.descriptive_name for spreadsheet in spreadsheets])

@spreadsheet_blueprint.route('/get_spreadsheets', methods=['POST'])
@timeit
@ajax_requires_account_or_share
def get_spreadsheets(user=None):

    data = json.loads(request.data)
    spreadsheet_ids = data['spreadsheet_ids']

    if not spreadsheet_ids:
        return jsonify({"error": MISSING_SPREADSHEET_MESSAGE}), 400

    current_app.logger.info(f"Getting spreadsheets {spreadsheet_ids} for user {user.username}")

    spreadsheets = []
    for spreadsheet_id in spreadsheet_ids:
        spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
        if not spreadsheet:
            return access_not_permitted(get_spreadsheets.__name__, user, spreadsheet_id)

        # Populate
        spreadsheet.init_on_load()

        spreadsheets.append(spreadsheet)

    dfs, combined_index = Spreadsheet.join_spreadsheets(spreadsheets)

    # Gather all values except for the actual numerical data
    # Which is handled separately
    spreadsheet_values = []
    for spreadsheet, df in zip(spreadsheets, dfs):
        values = dict(
                     data=df[spreadsheet.get_data_columns()],
                     x_values=spreadsheet.x_values,
                     nitecap_q=df.nitecap_q,
                     nitecap_p=df.nitecap_p,
                     total_delta=df.total_delta,
                     amplitude=df.amplitude,
                     peak_time=df.peak_time,
                     labels=combined_index.to_list(),
                     descriptive_name=spreadsheet.descriptive_name,
                     timepoints_per_cycle=spreadsheet.timepoints,
                     num_timepoints=spreadsheet.num_timepoints or (spreadsheet.timepoints * spreadsheet.days), #TODO: this is a temporary work-around until 'days' is phased out
                     spreadsheet_id=spreadsheet.id,
                     view_id=spreadsheet.edit_version, #TODO: make edit_version/view_id names agree eventually
                     spreadsheet_note=spreadsheet.note,
                     visitor=user.is_visitor(),
                     id_col_labels=list(spreadsheet.get_id_columns(label=True)),
                     ids=df.iloc[:,spreadsheet.get_id_columns()].T,
                     column_headers=spreadsheet.get_data_columns(),
                     jtk_p=None,
                     jtk_q=None,
                     ars_p=None,
                     ars_q=None,
                     ls_p=None,
                     ls_q=None,
                     anova_p=None,
                     anova_q=None,
                     cosinor_p=None,
                     cosinor_q=None,
                     cosinor_x0=None,
                     cosinor_x1=None,
                     cosinor_x2=None,
                     stat_values=spreadsheet.get_stat_values().to_dict(orient='series'),
                    )
        spreadsheet_values.append(values)

    return dumps(spreadsheet_values)

@spreadsheet_blueprint.route('/get_mpv_spreadsheets', methods=['POST'])
@timeit
@ajax_requires_account_or_share
def get_mpv_spreadsheets(user=None):
    spreadsheet_ids = json.loads(request.data)['spreadsheet_ids']
    assert len(spreadsheet_ids) == 1

    if not spreadsheet_ids:
        return jsonify({"error": MISSING_SPREADSHEET_MESSAGE}), 400

    current_app.logger.info(f"Fetching MPV spreadsheets {', '.join(spreadsheet_ids)} for user {user.username}")

    spreadsheets = []
    for spreadsheet_id in spreadsheet_ids:
        spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
        if not spreadsheet:
            return access_not_permitted(get_mpv_spreadsheets.__name__, user, spreadsheet_id)

        # Populate
        spreadsheet.init_on_load()

        spreadsheets.append(spreadsheet)

    dfs, combined_index = Spreadsheet.join_spreadsheets(spreadsheets)

    # Gather all values except for the actual numerical data
    # Which is handled separately
    spreadsheet_values = []
    for spreadsheet, df in zip(spreadsheets, dfs):
        column_labels = spreadsheet.column_labels

        x_label_values = [i for i,label in enumerate(spreadsheet.possible_assignments)]
        values = dict(
                     data=df[spreadsheet.get_mpv_data_columns()],
                     categories=json.loads(spreadsheet.categorical_data),
                     group_assignments=spreadsheet.group_assignments,
                     group_membership=spreadsheet.group_membership,
                     possible_assignments=spreadsheet.possible_assignments,
                     x_label_values=x_label_values,
                     anova_p=df['anova_p'],
                     anova_q=df['anova_q'],
                     labels=combined_index.to_list(),
                     descriptive_name=spreadsheet.descriptive_name,
                     spreadsheet_id=spreadsheet.id,
                     spreadsheet_note=spreadsheet.note,
                     visitor=user.is_visitor(),
                     column_headers=spreadsheet.get_data_columns(),
                     stat_values=spreadsheet.get_stat_values().to_dict(orient='series'),
                    )
        spreadsheet_values.append(values)

    return dumps(spreadsheet_values)

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
    current_app.logger.warn(f"Deleting spreadsheet {spreadsheet_id} from user {user.email}")

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

@spreadsheet_blueprint.route('/share', methods=['POST'])
@ajax_requires_login
def share(user=None):
    """
    AJAX endpoint - shares one of the user's spreadsheets.  Incoming json specifies the spreadsheet id and the config
    to share.  Confirms that spreadsheet indeed belongs to the user and if so, returns a token which encrypts the
    spreadsheet id and cutoff.
    :param user:  Returned by the decorator.  Logged in user is required.
    :return: json {'share': <token>} unless the user's privileges are inadequate.
    """

    # Collect json data
    json_data = request.get_json()
    spreadsheet_ids = json_data.get('spreadsheet_ids', None)
    config = json_data.get('config', dict())

    # Bad data
    if not spreadsheet_ids:
        return jsonify({"error": MISSING_SPREADSHEET_MESSAGE}), 400

    # Attempt to access spreadsheet not owned.
    for spreadsheet_id in spreadsheet_ids:
        if not user.find_user_spreadsheet_by_id(spreadsheet_id):
            current_app.logger.warn(IMPROPER_ACCESS_TEMPLATE.substitute(user_id=user.id, endpoint=request.path, spreadsheet_id=spreadsheet_ids))
            return jsonify({"errors": SPREADSHEET_NOT_FOUND_MESSAGE}, 404)

    current_app.logger.info(f"Sharing spreadsheet {spreadsheet_ids} with config {config} from user {user.email}")
    share = Share(spreadsheet_ids, user.id, config)
    share.save_to_db()
    return jsonify({'share': share.id})


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
    share = Share.find_by_id(token)

    if share is None:
        # Try the old share token
        try:
            s = Serializer(os.environ['OLD_SECRET_KEY'])
            token_value = s.loads(token)
            user_id = token_value['user_id']
            spreadsheet_ids = token_value['spreadsheet_ids']
            valid = True
        except:
            valid = False

        if valid:
            current_app.logger.error(f"User attempted to access an old share token for spreadsheets {spreadsheet_ids} and user_id {user_id}")
            spreadsheet_ids_str = ','.join(spreadsheet_ids)
            url = url_for(".show_spreadsheet", spreadsheet_id=spreadsheet_ids_str, _external=True)
            errors.append("The URL you received no longer works as a share due to system upgrades. "
                "A permanent share can be obtained from the original spreadsheet's uploader. "
                "If you are the owner of these spreadsheets, you can generate a new share link at "
                f'{url}')
        else:
            current_app.logger.error(f"Invalid share URL identified with token {token}");
            errors.append("The URL you received does not work. It may have been mangled in transit. "
                      "Please request another share")
        current_app.logger.error(errors)
        return render_template('spreadsheets/upload_file.html', errors=errors)


    sharing_user = User.find_by_id(share.user_id)
    spreadsheet_ids = [int(id) for id in share.spreadsheet_ids_str.split(',')]
    config = json.loads(share.config_json)

    spreadsheets = []
    for spreadsheet_id in spreadsheet_ids:
        spreadsheet = sharing_user.find_user_spreadsheet_by_id(spreadsheet_id)

        if not spreadsheet or not sharing_user:
            current_app.logger.error(f"Invalid share URL with token {token}. Spreadsheets do not belong to given user.")
            errors.append("The URL you received does not work.  It may have been mangled in transit.  Please request "
                          "another share")
            return render_template('spreadsheets/upload_file.html', errors=errors)
        spreadsheets.append(spreadsheet)

    is_categorical = [spreadsheet.is_categorical() for spreadsheet in spreadsheets]
    if any(is_categorical) and not all(is_categorical):
        flash("Spreadsheets must all be categorical or all time-series.")
        return redirect(url_for('.display_spreadsheets'))

    # Updates the last-access time
    share.save_to_db()

    if all(is_categorical):
        return render_template('spreadsheets/show_mpv_spreadsheet.html',
                           spreadsheet_ids=spreadsheet_ids,
                           config=config,
                           share_token=share.id,
                           user_id=sharing_user.id,
                           NOTIFICATION_API_ENDPOINT=os.environ['NOTIFICATION_API_ENDPOINT'],
                           descriptive_names=[spreadsheet.descriptive_name for spreadsheet in spreadsheets])
    else:
        return render_template('spreadsheets/comparison.html',
                           spreadsheet_ids=spreadsheet_ids,
                           config=config,
                           share_token=share.id,
                           user_id=sharing_user.id,
                           NOTIFICATION_API_ENDPOINT=os.environ['NOTIFICATION_API_ENDPOINT'],
                           descriptive_names=[spreadsheet.descriptive_name for spreadsheet in spreadsheets])

@spreadsheet_blueprint.route('/copy_share/<string:token>', methods=['GET'])
@requires_account
def copy_share(token, user=None):
    """ Make a copy of a shared file `token' to the users acocunt """
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
    errors = []
    if not user:
        errors.append("We are unable to create your share at the present time.  Please try again later")
        current_app.logger.error("Spreadsheet share consumption issue, unable to identify or generate a user.")
        return render_template('spreadsheets/upload_file.html', errors=errors)

    # Load the share token
    try:
        share = Share.find_by_id(token)
    except Exception as e:
        current_app.logger.error(f"Invalid share URL identified with token {token}");
        current_app.logger.error(e)
        errors.append("The URL you received does not work.  It may have been mangled in transit.  Please request "
                      "another share")
        return render_template('spreadsheets/upload_file.html', error=errors)
    sharing_user = User.find_by_id(share.user_id)
    spreadsheet_ids = [int(id) for id in share.spreadsheet_ids_str.split(',')]

    # TODO: we don't use the config when copying
    #config = json.loads(share.config_json)

    current_app.logger.info(f"Copying shared spreadsheets {spreadsheet_ids} from {sharing_user.email}")

    # Load the shared spreadsheets
    spreadsheets = []
    for spreadsheet_id in spreadsheet_ids:
        spreadsheet = sharing_user.find_user_spreadsheet_by_id(spreadsheet_id)

        if not spreadsheet or not sharing_user:
            current_app.logger.error(f"Invalid share URL with token {token}. Spreadsheets do not belong to given user.")
            errors.append("The URL you received does not work.  It may have been mangled in transit.  Please request "
                          "another share")
            return render_template('spreadsheets/upload_file.html', errors=errors)
        spreadsheets.append(spreadsheet)

    is_categorical = [spreadsheet.is_categorical() for spreadsheet in spreadsheets]
    if any(is_categorical) and not all(is_categorical):
        flash("Spreadsheets must all be categorical or all time-series.")
        return redirect(url_for('.display_spreadsheets'))

    # Updates the last-access time of the share
    share.save_to_db()

    # Create a copy of the sharing user's spreadsheet for the current user.nitecap
    shared_spreadsheet_ids = []
    for spreadsheet in spreadsheets:
        shared_spreadsheet = Spreadsheet.make_share_copy(spreadsheet, user)
        if shared_spreadsheet:
            shared_spreadsheet_ids.append(shared_spreadsheet.id)
        else:
            errors.append("The spreadsheet could not be copied to ues account.")
            return render_template('spreadsheets/upload_file.html', errors=errors)

    # Show the copied spreadsheets
    spreadsheet_ids_str = ','.join(str(id) for id in shared_spreadsheet_ids)
    return redirect(url_for('spreadsheets.show_spreadsheet', spreadsheet_id=spreadsheet_ids_str))


@spreadsheet_blueprint.route('/get_upside', methods=['POST'])
@timeit
@ajax_requires_account_or_share
def get_upside(user=None):
    # TODO: remove this eventually when using the computation backend

    comparisons_directory = os.path.join(user.get_user_directory_path(), "comparisons")
    if not os.path.exists(comparisons_directory):
        os.makedirs(comparisons_directory, exist_ok=True)

    spreadsheet_ids = json.loads(request.data)['spreadsheet_ids']

    # Run Upside dampening analysis, if it hasn't already been stored to disk
    upside_p_list = []
    upside_q_list = []
    spreadsheets = []

    # Check user ownership over these spreadsheets
    for spreadsheet_id in spreadsheet_ids:
        spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
        if not spreadsheet:
            current_app.logger.warn(f"Attempted access for spreadsheet {spreadsheet_id} not owned by user {user.id}")
            return jsonify({'error': "No such spreadsheet"})

        spreadsheet.init_on_load()
        spreadsheets.append(spreadsheet)

    dfs, combined_index = Spreadsheet.join_spreadsheets(spreadsheets)

    anova_p = None
    anova_q = None
    main_effect_p = None
    main_effect_q = None
    for primary, secondary in [(0, 1), (1, 0)]:
        primary_id, secondary_id = spreadsheet_ids[primary], spreadsheet_ids[secondary]
        file_path = os.path.join(comparisons_directory, f"{primary_id}v{secondary_id}.comparison.parquet")
        try:
            # Load comparison results
            comp_data = pyarrow.parquet.read_pandas(file_path).to_pandas()
            #Align indexes with spreadsheets
            comp_data = comp_data.loc[combined_index]
            # Populate the values
            upside_p_list.append(comp_data["upside_p"].values.tolist())
            upside_q_list.append(comp_data["upside_q"].values.tolist())
            anova_p = comp_data["two_way_anova_p"]
            anova_q = comp_data["two_way_anova_q"]
            phase_p = comp_data["phase_p"]
            main_effect_p = comp_data["main_effect_p"]
            main_effect_q = comp_data["main_effect_q"]
            phase_q = comp_data["phase_q"]
            amplitude_p = comp_data["amplitude_p"]
            amplitude_q = comp_data["amplitude_q"]
            current_app.logger.info(f"Loaded upside values from file {file_path}")
        except (OSError, KeyError) as e: # Parquet file could not be read (hasn't been written yet)
            # Trigger the job to compute these
            job_params = [user.id, spreadsheet_ids, [spreadsheet.edit_version for spreadsheet in spreadsheets]]
            job = Job.find_or_make("comparison", job_params)
            status = job.run()
            if status in ['failed', 'timed_out']:
                return jsonify({'status': status}), 500
            if status == 'completed':
                # If it says completed, we actually return 'running' since we couldn't
                # load the data off the disk so just need to try again
                status = 'running'
            return jsonify({'status': status}), 200

    return dumps({'status': 'completed',
                'upside_p': upside_p_list,
                'upside_q': upside_q_list,
                'two_way_anova_p': anova_p.tolist(),
                'two_way_anova_q': anova_q.tolist(),
                'main_effect_p': main_effect_p.tolist(),
                'main_effect_q': main_effect_q.tolist(),
                'phase_p': phase_p.tolist(),
                'phase_q': phase_q.tolist(),
                'amplitude_p': amplitude_p.tolist(),
                'amplitude_q': amplitude_q.tolist()
            })


@spreadsheet_blueprint.route('/run_pca', methods=['POST'])
@ajax_requires_account_or_share
def run_pca(user=None):
    args = json.loads(request.data)
    spreadsheet_ids = args['spreadsheet_ids']
    selected_genes = args['selected_genes']
    take_zscore = args['take_zscore']
    take_log_transform = args['take_logtransform']

    current_app.logger.info(f"Computing PCA from spreadsheets {spreadsheet_ids} of user {user.email}")

    if not spreadsheet_ids:
        return jsonify({"error": MISSING_SPREADSHEET_MESSAGE}), 400

    spreadsheets = []
    for spreadsheet_id in spreadsheet_ids:
        spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
        if not spreadsheet:
            return access_not_permitted(run_pca.__name__, user, spreadsheet_id)

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
@timeit
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
    spreadsheet.init_on_load()

    non_unique_ids = spreadsheet.find_replicate_ids(id_columns)
    current_app.logger.debug(f"Non-unique ids {non_unique_ids}")
    return jsonify({'non-unique_ids': non_unique_ids})

@spreadsheet_blueprint.route('/get_valid_comparisons', methods=['POST'])
@ajax_requires_account
def get_valid_comparisons(user=None):
    """
    AJAX endpoint that gives a list of spreadsheets that can be compared to
    among those that the user has
    """


    data = json.loads(request.data)
    spreadsheet_ids = data['spreadsheet_ids']

    current_app.logger.info(f"Finding the valid comparisons for spreadsheet {spreadsheet_ids} of user {user.email}")

    if not spreadsheet_ids:
        return jsonify({"error": MISSING_SPREADSHEET_MESSAGE}), 400

    # We just look at the first spreadsheet
    spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_ids[0])
    if not spreadsheet:
        return access_not_permitted(get_valid_comparisons.__name__, user, spreadsheet_id)

    # Check what other spreadsheets the user has
    valid_comparisons = []
    for other_spreadsheet in user.spreadsheets:
        if other_spreadsheet.id == spreadsheet.id:
            continue # Can't compare to oneself

        # Only suggest spreadsheets with the same layout
        # NOTE: doesn't check for compatibility of, say, ids
        if (other_spreadsheet.timepoints == spreadsheet.timepoints and
            other_spreadsheet.repeated_measures == spreadsheet.repeated_measures and
            other_spreadsheet.days == spreadsheet.days):

            valid_comparisons.append({
                "id": other_spreadsheet.id,
                "name": other_spreadsheet.descriptive_name,
                "original_filename": other_spreadsheet.original_filename,
            })
    return jsonify(valid_comparisons)



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


@spreadsheet_blueprint.route('/upload_mpv_file', methods=['GET', 'POST'])
def upload_mpv_file():
    current_app.logger.info('Uploading mpv spreadsheet')

    errors = []
    categorical_data = []

    # Spreadsheet file form submitted
    if request.method == 'POST':
        data_row = request.form.get('data_row', None)
        if not data_row or not data_row.isdigit() or int(data_row) < 1:
            errors.append(f"The value of the first data row is required and must be a positive integer.")
        upload_file = request.files.get('upload_file', None)
        if not upload_file or not len(upload_file.filename):
            errors.append(MISSING_SPREADSHEET_MESSAGE)
        if not allowed_file(upload_file.filename):
            errors.append(FILE_EXTENSION_ERROR)
        categorical_data, categorical_data_errors = collect_and_validate_categorical_data(request.form)
        if categorical_data_errors:
            errors.extend(categorical_data_errors)
        if errors:
            return render_template('spreadsheets/upload_mpv_file.html', data_row=data_row,
                                   categorical_data=categorical_data, errors=errors)

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
            return render_template('spreadsheets/upload_mpv_file.html', data_row=data_row,
                                   errors=[FILE_UPLOAD_ERROR])

        directory_path = pathlib.Path(os.path.join(user.get_user_directory_path(), f"{uuid.uuid4().hex}"))
        directory_path.mkdir(parents=True, exist_ok=True)

        # Rename the uploaded file and reattach the extension
        extension = Path(upload_file.filename).suffix
        file_path = os.path.join(directory_path, f"uploaded_spreadsheet{extension}")
        upload_file.save(file_path)

        # If the mime type validation fails, remove the directory containing the uploaded file from the disk
        file_mime_type, errors = validate_mime_type(file_path)
        if errors:
            shutil.rmtree(directory_path)
            return render_template('spreadsheets/upload_mpv_file.html', data_row=data_row, errors=errors)

        # For some files masquerading as one of the acceptable file types by virtue of its file extension, we
        # may only be able to identify it as such when pandas fails to parse it while creating a spreadsheet object.
        # We throw the directory containing the file away and report the error.
        try:
            spreadsheet = Spreadsheet(descriptive_name=upload_file.filename,
                                      days=None,
                                      timepoints=None,
                                      num_timepoints=None,
                                      repeated_measures=False,
                                      header_row=int(data_row)-1,
                                      original_filename=upload_file.filename,
                                      file_mime_type=file_mime_type,
                                      uploaded_file_path=file_path,
                                      spreadsheet_data_path=str(directory_path),
                                      categorical_data=json.dumps(categorical_data),
                                      user_id=user_id)
        except NitecapException as ne:
            current_app.logger.error(f"NitecapException {ne}")
            shutil.rmtree(directory_path)
            return render_template('spreadsheets/upload_mpv_file.html', data_row=data_row, errors=[FILE_UPLOAD_ERROR])

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

        return redirect(url_for('.collect_mpv_data', spreadsheet_id=spreadsheet.id))

    # Display spreadsheet file form
    return render_template('spreadsheets/upload_mpv_file.html', categorical_data=categorical_data)

@spreadsheet_blueprint.route('/collect_mpv_data/<spreadsheet_id>', methods=['GET', 'POST'])
@requires_account
def collect_mpv_data(spreadsheet_id, user=None):
    spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)

    # If the spreadsheet is not verified as owned by the user, the user is either returned to the his/her
    # spreadsheet list (in the case of a logged in user) or to the upload form (in the case of a visitor).
    if not spreadsheet:
        return access_not_permitted(collect_data.__name__, user, spreadsheet_id)

    categorical_data_labels = spreadsheet.get_categorical_data_labels()

    # Set up the dataframe
    spreadsheet.set_df()

    # Spreadsheet data form submitted.
    if request.method == 'POST':

        errors = validate_mpv_spreadsheet_data(request.form, spreadsheet)
        if errors:
            return render_template('spreadsheets/collect_mpv_data.html', errors=errors, labels=categorical_data_labels,
                                   spreadsheet=spreadsheet)

        spreadsheet.set_ids_unique()
        spreadsheet.save_to_db()
        spreadsheet.init_on_load()
        return redirect(url_for('.show_spreadsheet', spreadsheet_id=spreadsheet.id))
    return render_template('spreadsheets/collect_mpv_data.html', labels=categorical_data_labels, spreadsheet=spreadsheet)


def validate_mpv_spreadsheet_data(form_data, spreadsheet):
    """
    Helper method to collect form data and validate it
    :param form_data: the form dictionary from requests
    :return: a tuple consisting of the form data and an array of error msgs.  An empty array indicates no errors
    """

    # Gather data
    spreadsheet.descriptive_name = form_data.get('descriptive_name', None)
    spreadsheet.column_labels = [value for key, value in form_data.items() if key.startswith('col')]
    spreadsheet.column_labels_str = ','.join(spreadsheet.column_labels)

    # Check data for errors
    errors = []
    if not spreadsheet.descriptive_name:
        errors.append(f"A descriptive name is required.")
    error = spreadsheet.validate_categorical(spreadsheet.column_labels)
    if error:
        errors.append(error)
    return errors

def collect_and_validate_categorical_data(form_data):
    """
    Collect the categorical data and convert into a JSON object that can be stringified and stored in the database
    record for the spreadsheet.  Additionally validate that each categorical variable specified has at least 2
    possible values.  An example of the JSON object to be stringified:
        [
            {
                variable: 'pet',
                values: [
                    {
                        name: dog,
                        short_name: d
                    },
                    {
                        name: cat,
                        short_name: c
                    },
                    ...
                ]
            },
            ...
        ]
    :param form_data: form inputs
    :return: the JSON list (as above) containing the categorical data and a list of errors.  The error list is either
    empty or contains one or more error messages.
    """
    errors = []
    categorical_data = []
    categorical_variables = {int(key.split("_")[1]): value for key, value in form_data.items()
                             if key.startswith('categoricalVariable')}

    # note that categorical variable inputs are of the form 'categoricalVariable_n' where n is the index or position
    # of that categorical variable.
    for pos, var_name in categorical_variables.items():

        # note that possible value inputs are of the form 'choiceName_i_j' or 'choiceShort_i_j' where i is the index
        # or position of the parent categorical variable and j is the index/position of the possible value.
        if var_name:
            value_names = {int(key.split("_")[2]): value for key, value in form_data.items()
                           if key.startswith(f'choiceName_{pos}')}
            value_short_names = {int(key.split("_")[2]): value for key, value in form_data.items()
                           if key.startswith(f'choiceShort_{pos}')}
            values = []

            # It is permitted for the user not to fill in both the long and short names of a possible value.  In
            # such instances, the input provided is applied to both.
            for index in range(0, max([len(value_names.keys()), len(value_short_names.keys())])):
                value_name = value_names[index]
                value_short_name = value_short_names[index]
                if not value_name and not value_short_name:
                    continue
                if not value_name:
                    value_name = value_short_name
                if not value_short_name:
                    value_short_name = value_name
                value_item = {'name': value_name, 'short_name': value_short_name}
                values.append(value_item)

            # Each categorical variable should have at least 2 possible values.
            if not values or len(values) < 2:
                errors.append(f"Categorical variable {var_name} must have at least 2 possible values.")
            categorical_data.append({"variable": var_name, "values": values})
    return categorical_data, errors
