import magic
from flask import Blueprint, request, session, url_for, redirect, render_template, flash, send_file, jsonify
from pandas.errors import ParserError

from exceptions import NitecapException
from models.spreadsheets.spreadsheet import Spreadsheet
from werkzeug.utils import secure_filename
import os
from pathlib import Path
import pandas as pd
import uuid
from models.users.decorators import requires_login
from models.users.user import User
import json
from flask import current_app
import constants

import nitecap
spreadsheet_blueprint = Blueprint('spreadsheets', __name__)

@spreadsheet_blueprint.route('/load_spreadsheet', methods=['GET','POST'])
def load_spreadsheet():
    current_app.logger.info('Loading spreadsheet')
    if request.method == 'POST':
        # http: // flask.pocoo.org / docs / 1.0 / patterns / fileuploads /  # improving-uploads
        descriptive_name = request.form['descriptive_name']
        days = request.form['days']
        timepoints = request.form['timepoints']
        repeated_measures = request.form['repeated_measures']
        repeated_measures = True if repeated_measures == 'y' else False
        header_row = request.form['header_row']
        upload_file = request.files['upload_file'] if 'upload_file' in request.files else None

        # Validate and give errors
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
        if errors:
            return render_template('spreadsheets/spreadsheet_upload_form.html', errors=errors,
                                   descriptive_name=descriptive_name, days=days,
                                   timepoints=timepoints, repeated_measures=repeated_measures, header_row=header_row)

        # Not really necessary since we re-name the file.
        filename = secure_filename(upload_file.filename)

        extension = Path(filename).suffix
        new_filename = uuid.uuid4().hex + extension
        file_path = os.path.join(os.environ.get('UPLOAD_FOLDER'), new_filename)
        upload_file.save(file_path)

        # It appears that we can only verify the mime type of a file once saved.  We will delete it if it is found not
        # to be one of the accepted file mime types.
        disallowed_mime_type = f"Only comma or tab delimited files or Excel spreadsheets are accepted.  They may be gzipped."
        x = magic.Magic(mime=True)
        z = magic.Magic(mime=True, uncompress=True)
        file_mime_type = x.from_file(file_path)
        print(file_mime_type)
        if file_mime_type not in constants.ALLOWED_MIME_TYPES:
            errors.append(disallowed_mime_type)
        elif file_mime_type in constants.COMPRESSED_MIME_TYPES:
            file_mime_type = z.from_file(file_path)
            print(file_mime_type)
            if file_mime_type not in constants.ALLOWED_MIME_TYPES:
                errors.append(disallowed_mime_type)
        if errors:
            os.remove(file_path)
            return render_template('spreadsheets/spreadsheet_upload_form.html', errors=errors,
                                   descriptive_name=descriptive_name, days=days,
                                   timepoints=timepoints, repeated_measures=repeated_measures, header_row=header_row)

        # For some files masquerading as one of the acceptable file types by virtue of its file extension, we
        # may only be able to identify it when pandas fails to parse it while creating a spreadsheet object.
        # We throw the file away and report the error.
        user_id = None
        if 'email' in session and session['email']:
            user = User.find_by_email(session['email'])
            if user:
                user_id = user.id
        try:
            spreadsheet = Spreadsheet(descriptive_name=descriptive_name,
                                      days = days,
                                      timepoints = timepoints,
                                      repeated_measures = repeated_measures,
                                      header_row = header_row,
                                      original_filename = filename,
                                      file_mime_type = file_mime_type,
                                      uploaded_file_path = file_path,
                                      user_id = user_id)
        except NitecapException as ne:
            current_app.logger.error(f"NitecapException {ne}")
            os.remove(file_path)
            errors.append(ne.message)
            return render_template('spreadsheets/spreadsheet_upload_form.html', errors=errors, days=days, timepoints=timepoints)
        spreadsheet.save_to_db()
        session['spreadsheet_id'] = spreadsheet.id

        return redirect(url_for('.identify_spreadsheet_columns'))

    return render_template('spreadsheets/spreadsheet_upload_form.html')

def allowed_file(filename):
    extension = Path(filename).suffix
    return extension.lower() in constants.ALLOWED_EXTENSIONS

@spreadsheet_blueprint.route('spreadsheets/identify_spreadsheet_columns', methods=['GET','POST'])
def identify_spreadsheet_columns():
    errors = []

    if 'spreadsheet_id' not in session or not session['spreadsheet_id']:
        errors.append("You may only work with your own spreadsheet.")
        return render_template('spreadsheets/spreadsheet_upload_form.html', errors=errors)
    spreadsheet = Spreadsheet.find_by_id(session['spreadsheet_id'])
    if request.method == 'POST':
        column_labels = list(request.form.values())

        error, messages = spreadsheet.validate(column_labels)
        errors.extend(messages)
        if error:
            return render_template('spreadsheets/spreadsheet_columns_form.html', spreadsheet=spreadsheet, errors=errors)

        spreadsheet.identify_columns(column_labels)
        spreadsheet.set_ids_unique()
        spreadsheet.compute_nitecap()
        spreadsheet.save_to_db()
        return redirect(url_for('.set_spreadsheet_breakpoint'))
    return render_template('spreadsheets/spreadsheet_columns_form.html', spreadsheet=spreadsheet, errors=errors)


@spreadsheet_blueprint.route('/set_spreadsheet_breakpoint', methods=['GET','POST'])
def set_spreadsheet_breakpoint():
    errors = []
    if 'spreadsheet_id' not in session or not session['spreadsheet_id']:
        errors.append("You may only work with your own spreadsheet.")
        return render_template('spreadsheets/spreadsheet_upload_form.html', errors=errors)
    spreadsheet = Spreadsheet.find_by_id(session['spreadsheet_id'])
    if request.method == 'POST':
        row_index = int(request.form['row_index'])
        spreadsheet.breakpoint = row_index
        spreadsheet.save_to_db()
        session['spreadsheet'] = spreadsheet.to_json()
        return redirect(url_for('.display_heatmap'))

    data = spreadsheet.get_raw_data()
    max_value_filter = spreadsheet.max_value_filter if spreadsheet.max_value_filter else 'null'
    ids = list(spreadsheet.get_ids())
    return render_template('spreadsheets/spreadsheet_breakpoint_form.html',
                                data=data.to_json(orient='values'),
                                x_values=spreadsheet.x_values,
                                x_labels=spreadsheet.x_labels,
                                x_label_values=spreadsheet.x_label_values,
                                qs=json.dumps(list(spreadsheet.df.nitecap_q.values)),
                                ps=json.dumps(list(spreadsheet.df.nitecap_p.values)),
                                amplitudes=json.dumps(list(spreadsheet.df.amplitude.values)),
                                peak_times=json.dumps(list(spreadsheet.df.peak_time.values)),
                                anovas=json.dumps(list(spreadsheet.df.anova_p.values)),
                                filtered=json.dumps(spreadsheet.df.filtered_out.tolist()),
                                ids=ids,
                                column_pairs=spreadsheet.column_pairs,
                                breakpoint = spreadsheet.breakpoint if spreadsheet.breakpoint is not None else 0,
                                descriptive_name = spreadsheet.descriptive_name,
                                timepoints_per_day = spreadsheet.timepoints,
                                max_value_filter = max_value_filter)



@spreadsheet_blueprint.route('/show_spreadsheet/<int:spreadsheet_id>', methods=['GET','POST'])
@requires_login
def show_spreadsheet(spreadsheet_id):
    errors = []
    user = User.find_by_email(session['email'])
    spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)

    if not spreadsheet:
        errors.append('You may only manage your own spreadsheets.')
        return render_template('spreadsheets/user_spreadsheets.html', user=user, errors=errors)
    if request.method == 'POST':
        row_index = int(request.form['row_index'])
        spreadsheet.breakpoint = row_index
        spreadsheet.save_to_db()
        return redirect(url_for('.display_heatmap'))

    session["spreadsheet_id"] = spreadsheet.id

    data = spreadsheet.get_raw_data()
    max_value_filter = spreadsheet.max_value_filter if spreadsheet.max_value_filter else 'null'
    ids = list(spreadsheet.get_ids())
    return render_template('spreadsheets/spreadsheet_breakpoint_form.html',
                                data=data.to_json(orient='values'),
                                x_values=spreadsheet.x_values,
                                x_labels=spreadsheet.x_labels,
                                x_label_values=spreadsheet.x_label_values,
                                qs=json.dumps(list(spreadsheet.df.nitecap_q.values)),
                                ps=json.dumps(list(spreadsheet.df.nitecap_p.values)),
                                amplitudes=json.dumps(list(spreadsheet.df.amplitude.values)),
                                peak_times=json.dumps(list(spreadsheet.df.peak_time.values)),
                                anovas=json.dumps(list(spreadsheet.df.anova_p.values)),
                                filtered=json.dumps(spreadsheet.df.filtered_out.tolist()),
                                ids=ids,
                                column_pairs=spreadsheet.column_pairs,
                                breakpoint = spreadsheet.breakpoint if spreadsheet.breakpoint is not None else 0,
                                descriptive_name=spreadsheet.descriptive_name,
                                timepoints_per_day = spreadsheet.timepoints,
                                max_value_filter = max_value_filter)


@spreadsheet_blueprint.route('/heatmap', methods=['POST'])
def display_heatmap():
    errors = []
    json_data = request.get_json()
    row_index = json_data.get('row_index',0)
    spreadsheet = Spreadsheet.find_by_id(session['spreadsheet_id'])
    spreadsheet.breakpoint = row_index
    spreadsheet.save_to_db()
    data, labels, original_indexes = spreadsheet.reduce_dataframe(spreadsheet.breakpoint)
    data = spreadsheet.normalize_data(data)
    combined_data = spreadsheet.average_replicates(data)
    heatmap_x_values = []
    for day in range(spreadsheet.days):
        for timepoint in range(spreadsheet.timepoints):
             num_replicates = spreadsheet.num_replicates[timepoint]
             for rep in range(num_replicates):
                 heatmap_x_values.append(f"Day{day + 1} Timepoint{timepoint + 1} Rep{rep + 1}")
    heatmap_data = data.where((pd.notnull(data)), None).values.tolist()
    heatmap_combined_data = combined_data.where((pd.notnull(combined_data)), None).values.tolist()
    return jsonify(
                        {
                            "heatmap_labels": labels,
                            "heatmap_data": heatmap_data,
                            "heatmap_combined_data": heatmap_combined_data,
                            "heatmap_x_values": heatmap_x_values,
                            "heatmap_indexes": list(original_indexes)
                        }
                    )



@spreadsheet_blueprint.route('/jtk', methods=['POST'])
def get_jtk():
    errors = []
    json_data = request.get_json()
    row_index = json_data.get('row_index',0)
    spreadsheet = Spreadsheet.find_by_id(session['spreadsheet_id'])
    spreadsheet.breakpoint = row_index
    spreadsheet.save_to_db()
    jtk_ps, jtk_qs = spreadsheet.get_jtk()
    return jsonify( { "jtk_ps": jtk_ps,
                      "jtk_qs": jtk_qs } )

@spreadsheet_blueprint.route('/display_spreadsheets', methods=['GET'])
@requires_login
def display_spreadsheets():
    print("Display spreadsheets {session['email']}")
    user = User.find_by_email(session['email'])
    return render_template('spreadsheets/user_spreadsheets.html', user=user)


@spreadsheet_blueprint.route('/delete/<int:spreadsheet_id>', methods=['GET'])
@requires_login
def delete(spreadsheet_id):
    """
    The spreadsheet deletion is intended only for logged in users and is activated via a trashcan
    icon alongside each spreadsheet in the user's spreadsheet list.  That the spreadsheet to be
    deleted belongs to the user making the request is verified.  If so verified, the spreadsheet is
    deleted first from the database and then the originally uploaded spreadsheet file and the
    processed spreadsheet file are removed from the file system.  The user is notified in the event
    on an incomplete removal.
    :param spreadsheet_id: the spreadsheet id to be removed
    """
    errors = []
    user = User.find_by_email(session['email'])
    spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
    if not spreadsheet:
        errors.append('You may only manage your own spreadsheets.')
        current_app.logger.warn(f"User {user.id} attempted to delete spreadsheet {spreadsheet_id}")
        return render_template('spreadsheets/user_spreadsheets.html', user=user, errors=errors)
    try:
        spreadsheet.delete_from_db()
        os.remove(spreadsheet.file_path)
        os.remove(spreadsheet.uploaded_file_path)
    except Exception as e:
       errors.append("The spreadsheet data may not have been all successfully removed.")
       current_app.logger.error(f"The data for spreadsheet {spreadsheet_id} could not all be successfully "
                                f"expunged.", e)
    if errors:
        return render_template('spreadsheets/user_spreadsheets.html', user=user, errors=errors)
    return redirect(url_for('.display_spreadsheets'))


@spreadsheet_blueprint.route('/download', methods=['GET'])
def download_spreadsheet():
    """
    Response to a request from the graphs page to download the spreadsheet whose id is in the session.  In this case,
    the user need not be logged in.  Nevertheless, the requested spreadsheet must be in the user's inventory.  In the
    case of a visitor, the spreadsheet must not be in the inventory of any logged in user.  If the user is authorized
    to download the spreadsheet and the file is available, the file representing the fully processed version of the
    spreadsheet is delivered as an attachment.
    """
    errors = []
    spreadsheet_id = session['spreadsheet_id']
    user = User.find_by_email(session['email'])
    spreadsheet = None
    if user:
        spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
        if not spreadsheet:
            errors.append('You may only manage your own spreadsheets.')
            current_app.logger.warn(f"User {user.id} attempted to download spreadsheet {spreadsheet_id}")
            return render_template('spreadsheets/user_spreadsheets.html', user=user, errors=errors)
    else:
        spreadsheet = Spreadsheet.find_by_id(spreadsheet_id)
        if not spreadsheet:
            errors.append('The requested spreadsheet could not be found')
            return render_template('spreadsheets/spreadsheet_upload_form.html', errors=errors)
        if spreadsheet.owned():
            errors.append('You may only manage your own spreadsheets.')
            current_app.logger.warn(f"Visitor attempted to download spreadsheet {spreadsheet_id}")
            return render_template('spreadsheets/spreadsheet_upload_form.html', errors=errors)
    try:
        return send_file(spreadsheet.file_path, as_attachment=True, attachment_filename='processed_spreadsheet.txt')
    except Exception as e:
        errors.append("The processed spreadsheet data could not be downloaded.")
        current_app.logger.error(f"The processed spreadsheet data for spreadsheet {spreadsheet_id} could not be "
                                 f"downloaded.", e)
        return render_template('spreadsheets/spreadsheet_upload_form.html', errors=errors)


@spreadsheet_blueprint.route('/download/<int:spreadsheet_id>', methods=['GET'])
@requires_login
def download(spreadsheet_id):
    """
    Response to a request from the spreadsheet listing page to download the spreadsheet whose id is given in the url.
    The user must be logged in.  Additionally, the requested spreadsheet must be in the logged in user's inventory.  If
    it is and the file is available, the file representing the fully processed version of the spreadsheet is delivered
    as an attachment.
    :param spreadsheet_id: the id of the spreadsheet to download
    """
    errors = []
    user = User.find_by_email(session['email'])
    spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
    if not spreadsheet:
        errors.append('You may only manage your own spreadsheets.')
        current_app.logger.warn(f"User {user.id} attempted to download spreadsheet {spreadsheet_id}")
        return render_template('spreadsheets/user_spreadsheets.html', user=user, errors=errors)
    try:
        return send_file(spreadsheet.file_path, as_attachment=True, attachment_filename='processed_spreadsheet.txt')
    except Exception as e:
        errors.append("The processed spreadsheet data could not be downloaded.")
        current_app.logger.error(f"The processed spreadsheet data for spreadsheet {spreadsheet_id} could not be "
                                 f"downloaded.", e)
        return render_template('spreadsheets/user_spreadsheets.html', user=user, errors=errors)


@spreadsheet_blueprint.route('/edit/<int:spreadsheet_id>', methods=['GET', 'POST'])
@requires_login
def edit_details(spreadsheet_id):
    """
    Allows a logged in user to edit the details of an existing spreadsheet (e.g., name, # days, # timepoints, etc).  A
    check is made to insure that the spreadsheet id sent in the url identified a spreadsheet in the logged in user's
    inventory.
    :param spreadsheet_id:  id to the spreadsheet whose details the logged in user wishes to edit.
    """
    errors = []
    user = User.find_by_email(session['email'])
    spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
    if not spreadsheet:
        errors.append('You may only manage your own spreadsheets.')
        current_app.logger.warn(f"User {user.id} attempted to edit details for spreadsheet {spreadsheet_id}")
        return render_template('spreadsheets/user_spreadsheets.html', user=user, errors=errors)
    session['spreadsheet_id'] = spreadsheet_id
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


@spreadsheet_blueprint.route('/edit', methods=['GET', 'POST'])
@requires_login
def edit_columns():
    """
    Allows a logged in user to edit the columns of an existing spreadsheet.  The spreadsheet in the session is
    verified first as belonging to the user making this request.  The column labels selected by the user are
    validated.  The user is returned to the column edit form with error messages should validation fail.  Otherwise,
    nitecap calculations are re-done in accordance with the modified column labels and the user is redirected to the
    show spreadsheet method.
    """
    errors = []
    user = User.find_by_email(session['email'])
    spreadsheet = user.find_user_spreadsheet_by_id(session['spreadsheet_id'])
    if not spreadsheet:
        errors.append('You may only manage your own spreadsheets.')
        current_app.logger.warn(f"User {user.id} attempted to edit the column labels of spreadsheet "
                                f"{session['spreadsheet_id']}")
        return render_template('spreadsheets/user_spreadsheets.html', user=user, errors=errors)
    if request.method == 'POST':
        column_labels = list(request.form.values())
        error, messages = spreadsheet.validate(column_labels)
        errors.extend(messages)
        if errors:
            return render_template('spreadsheets/edit_columns_form.html', spreadsheet=spreadsheet, errors=errors)
        spreadsheet.identify_columns(column_labels)
        spreadsheet.set_ids_unique()
        spreadsheet.compute_nitecap()
        spreadsheet.save_to_db()
        return redirect(url_for('.show_spreadsheet', spreadsheet_id=spreadsheet.id))
    return render_template('spreadsheets/edit_columns_form.html', spreadsheet=spreadsheet)


@spreadsheet_blueprint.route('/save_filters', methods=['POST'])
def save_filters():
    """
    Response to ajax request to apply filters set on the graphs page.  Those filter values are also saved to the
    spreadsheet entry in the database.  The call may be made by both logged in users and visitors (annoymous user).
    :return: A json string containing filtered values along with associated q values and p values.
    """
    json_data = request.get_json()
    max_value_filter = json_data.get('max_value_filter', None)
    spreadsheet = Spreadsheet.find_by_id(session['spreadsheet_id'])
    spreadsheet.max_value_filter = max_value_filter
    spreadsheet.apply_filters()
    spreadsheet.save_to_db()
    response = jsonify({'qs': [x if x == x else None for x in list(spreadsheet.df.nitecap_q.values)],
                        'ps': [x if x == x else None for x in list(spreadsheet.df.nitecap_p.values)],
                        'filtered': spreadsheet.df.filtered_out.values.tolist()})
    return response


@spreadsheet_blueprint.route('/share', methods=['POST'])
@requires_login
def share():
    """
    Response to ajax request by logged in user to share one of the user's spreadsheets.  Incoming json specifies the
    spreadsheet to share.  Confirm that it indeed belongs to the user and if so, returns a token which encrypts the
    spreadsheet id.
    :return: json {'share': <token>}
    """
    errors = []
    user = User.find_by_email(session['email'])
    json_data = request.get_json()
    spreadsheet_id = json_data.get('spreadsheet_id', None)
    print(f"Spreadsheet {spreadsheet_id}")
    if not user.find_user_spreadsheet_by_id(spreadsheet_id):
        errors.append('You may only manage your own spreadsheets.')
        return jsonify({"errors": errors}, 401)
    return jsonify({'share': user.get_share_token(spreadsheet_id)})


@spreadsheet_blueprint.route('/share/<string:token>', methods=['GET'])
def consume_share(token):
    """
    Response to a standard get request to obtain a shared spreadsheet.  The token is verified and the spreadsheet is
    checked against the sharing user's inventory to be sure that the spreadsheet still exists and is in fact, owned
    by the sharing user.  If either the sharing user does not exist or the spreadsheet to be sharing does not exist in
    the sharing user's inventory, the receiving user is directed to the upload spreadsheet page and informed that the
    token was not comprehensible.  Otherwise a copy of all facets of the spreadsheet is made and assigned to the
    receiving user (if logged in) or to the annonymous user.  The logged in receiving user is taken to the show
    spreadsheet method while the non-logged in user is taken to the set spreadsheet breakpoint method since logged
    in users and visitors are handled differently.  If a visitor chooses to login before abandoning the spreadsheet, the
    spreadsheet will be added to that receiving user's inventory.  The sharing user has no control over further
    dissemination.
    :param token: the share token given to the receiving user
    """
    errors = []
    sharing_user, spreadsheet_id = User.verify_share_token(token)
    spreadsheet = sharing_user.find_user_spreadsheet_by_id(spreadsheet_id)
    if not spreadsheet or not sharing_user:
        errors.append("The token you received does not work.  It may have been mangled in transit.  Please request"
                      "another share")
        return render_template('spreadsheets/spreadsheet_upload_form.html', errors=errors)
    user = None
    if 'email' in session:
        user = User.find_by_email(session['email'])
    shared_spreadsheet = Spreadsheet.make_share_copy(spreadsheet, user.id if user else None)
    session['spreadsheet_id'] = shared_spreadsheet.id
    if user and shared_spreadsheet:
        return redirect(url_for('spreadsheets.show_spreadsheet', spreadsheet_id=shared_spreadsheet.id))
    if not user and shared_spreadsheet:
        return redirect(url_for('spreadsheets.set_spreadsheet_breakpoint'))
    errors.append("The spreadsheets could not be shared.")
    return render_template('spreadsheets/spreadsheet_upload_form.html', errors=errors)

@spreadsheet_blueprint.route('/compare', methods=['GET'])
@requires_login
def compare():
    errors = []
    spreadsheets = []
    non_unique_id_counts = []
    datasets = []
    x_values = []
    x_labels = []
    x_label_values = []
    column_pairs = []
    columns = []
    datasets = []
    user = User.find_by_email(session['email'])
    spreadsheet_ids = request.args.get('spreadsheet_ids').split(",")
    for spreadsheet_id in spreadsheet_ids:
        spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
        if not spreadsheet:
            errors.append('You may only manage your own spreadsheets.')
            return render_template('spreadsheets/user_spreadsheets.html', user=user, errors=errors)
        spreadsheets.append(spreadsheet)
    errors = Spreadsheet.check_for_timepoint_consistency(spreadsheets)
    if errors:
        return render_template('spreadsheets/user_spreadsheets.html', user=user, errors=errors)

    descriptive_names = []
    for spreadsheet in spreadsheets:
        non_unique_ids = spreadsheet.find_replicate_ids()
        non_unique_id_counts.append(len(non_unique_ids))
        print(f"Number of non unique ids is {len(non_unique_ids)}")
        x_values.append(spreadsheet.x_values)
        x_labels.append(spreadsheet.x_labels)
        x_label_values.append(spreadsheet.x_label_values)
        column_pairs.append(spreadsheet.column_pairs)
        descriptive_names.append(spreadsheet.descriptive_name)
        data = spreadsheet.df
        data["compare_ids"] = list(spreadsheet.get_ids())
        print(f"Shape prior to removal of non-unique ids: {data.shape}")
        data = data.set_index("compare_ids")
        data = data[~data.index.duplicated()]
        datasets.append(data)
        print(f"Shape prior to join with label col: {data.shape}")


    if not set(datasets[0].index) & set(datasets[1].index):
        errors.append("The spreadsheets have no IDs in common.  Perhaps the wrong column was selected as the ID?")
        return render_template('spreadsheets/user_spreadsheets.html', user=user, errors=errors)

    common_columns = set(datasets[0].columns).intersection(set(datasets[1].columns))
    df = datasets[0].join(datasets[1], how='inner', lsuffix='_0', rsuffix='_1')
    df = df.sort_values(by=['total_delta_0'])
    print(f"Shape after join: {df.shape}")
    compare_ids = df.index.tolist()
    datasets = []
    qs = []
    ps = []
    amplitudes = []
    peak_times = []
    anovas = []
    for i in [0,1]:
        columns.append([column + f"_{i}" if column in common_columns else column
                            for column in spreadsheets[i].get_data_columns()])
        datasets.append(df[columns[i]].values)
        qs.append(df[f"nitecap_q_{i}"].values.tolist())
        ps.append(df[f"nitecap_p_{i}"].values.tolist())
        amplitudes.append(df[f"amplitude_{i}"].values.tolist())
        peak_times.append(df[f"peak_time_{i}"].values.tolist())
        anovas.append(df[f"anova_p_{i}"].values.tolist())


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
                           anovas=json.dumps(anovas),
                           filtered=json.dumps(spreadsheets[0].df.filtered_out.tolist()),
                           spreadsheet_ids=json.dumps(spreadsheet_ids))

@spreadsheet_blueprint.route('/get_upside', methods=['POST'])
def get_upside():
    spreadsheet_ids = json.loads(request.data)['spreadsheet_ids']

    # Run Upside dampening analysis, if it hasn't already been stored to disk
    upside_ps = []
    datasets = []
    spreadsheets = []

    # Check user ownership over these spreadsheets
    user = User.find_by_email(session['email'])
    for spreadsheet_id in spreadsheet_ids:
        spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
        if not spreadsheet:
            current_app.logger.info("Attempted access for spreadsheet {spreadsheet_id} not owned by user")
            return jsonify( {'upside_ps': null} )
        spreadsheets.append(spreadsheet)

    for primary, secondary in [(0,1), (1,0)]:
        primary_id, secondary_id = spreadsheet_ids[primary], spreadsheet_ids[secondary]
        file_path = os.path.join(os.environ.get('UPLOAD_FOLDER'), f"{primary_id}v{secondary_id}.comparison.txt")
        try:
            comp_data = pd.read_table(file_path)
            upside_ps.append(comp_data["upside_ps"].values.tolist())
            current_app.logger.info(f"Loaded upside values from file {file_path}")
        except FileNotFoundError:
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

                for i in [0,1]:
                    columns = [column + f"_{i}" if column in common_columns else column
                                        for column in spreadsheets[i].get_data_columns()]
                    datasets.append(df[columns].values)

            # Run the actual upside calculation
            current_app.logger.info(f"Dataset sizes: {df.shape}, {datasets[primary].shape}, {datasets[secondary].shape}")
            upside_p = nitecap.upside.main(spreadsheets[primary].num_replicates, datasets[primary],
                                spreadsheets[secondary].num_replicates, datasets[secondary])
            comp_data = pd.DataFrame(index = df.index)
            comp_data["upside_ps"] = upside_p
            comp_data.to_csv(file_path, sep="\t")
            upside_ps.append(upside_p.tolist())
            current_app.logger.info("Compute upside values and saved them to file {file_path}")

    return jsonify({
                'upside_ps': upside_ps
            })
    

@spreadsheet_blueprint.route('/check_id_uniqueness', methods=['POST'])
def check_id_uniqueness():
    user = User.find_by_email(session['email'])
    user = user if user else User.find_by_username("annonymous")
    spreadsheet = None
    errors = []
    json_data = request.get_json()
    spreadsheet_id = json_data.get('spreadsheet_id', None)
    id_columns = json_data.get('id_columns', None)
    if not id_columns or len(id_columns) == 0:
        errors.append("No id columns were selected. Please select at least one id column.")
    if not spreadsheet_id:
        errors.append("No spreadsheet was identified. Make sure you are selecting one you uploaded.")
    else:
        spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
    if not spreadsheet:
       errors.append('The spreadsheet being edited could not be found.')
    if errors:
        print(errors)
        return jsonify({'errors': errors}), 404
    non_unique_ids = spreadsheet.find_replicate_ids(id_columns)
    print(non_unique_ids)
    return jsonify({'non-unique_ids': non_unique_ids})
