import magic
from flask import Blueprint, request, session, url_for, redirect, render_template, flash, send_file, jsonify
from pandas.errors import ParserError

from models.spreadsheets.spreadsheet import Spreadsheet
from werkzeug.utils import secure_filename
import os
from pathlib import Path
import pandas as pd
import uuid
import constants
from models.users.user import User

spreadsheet_blueprint = Blueprint('spreadsheets', __name__)

@spreadsheet_blueprint.route('/load_spreadsheet', methods=['GET','POST'])
def load_spreadsheet():
    print("Loading spreadsheet")
    if request.method == 'POST':
        # http: // flask.pocoo.org / docs / 1.0 / patterns / fileuploads /  # improving-uploads
        days = request.form['days']
        timepoints = request.form['timepoints']
        upload_file = request.files['upload_file'] if 'upload_file' in request.files else None

        # Validate and give errors
        errors = []

        if not days.isdigit():
            errors.append(f"The value for days is required and must be a positve integer.")
        if not timepoints.isdigit():
            errors.append(f"The value for timepoints is required and must be a positve integer.")
        if not upload_file:
            errors.append(f'No spreadsheet file was provided.')
        else:
            if not len(upload_file.filename):
                errors.append('No spreadsheet file was provided.')
            if not allowed_file(upload_file.filename):
                errors.append(f"File must be one of the following types: {', '.join(constants.ALLOWED_EXTENSIONS)}")
        if errors:
            return render_template('spreadsheets/spreadsheet_upload_form.html', errors=errors, days=days, timepoints=timepoints)

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
            return render_template('spreadsheets/spreadsheet_upload_form.html', errors=errors, days=days,
                                   timepoints=timepoints)

        # For some files masquerading as one of the acceptable file types by virtue of its file extension, we
        # may only be able to identify it when pandas fails to parse it while creating a spreadsheet object.
        # We throw the file away and report the error.
        user_id = None
        if 'email' in session and session['email']:
            user = User.find_by_email(session['email'])
            if user:
                user_id = user.id
        try:
            spreadsheet = Spreadsheet(days, timepoints, filename, uploaded_file_path = file_path, user_id=user_id)
        except (UnicodeDecodeError, ParserError) as e:
            print(type(e), e)
            os.remove(file_path)
            errors.append(f"The file provided is not parseable.")
            return render_template('spreadsheets/spreadsheet_upload_form.html', errors=errors, days=days, timepoints=timepoints)
        spreadsheet.save_to_db()
        session['spreadsheet_id'] = spreadsheet.id

        return redirect(url_for('.identify_spreadsheet_columns'))

    return render_template('spreadsheets/spreadsheet_upload_form.html')

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in constants.ALLOWED_EXTENSIONS

@spreadsheet_blueprint.route('spreadsheets/identify_spreadsheet_columns', methods=['GET','POST'])
def identify_spreadsheet_columns():
    errors = []
    #spreadsheet = Spreadsheet.from_json(session['spreadsheet'])
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

        spreadsheet.compute_ordering()
        #session['spreadsheet'] = spreadsheet.to_json()
        spreadsheet.save_to_db()
        return redirect(url_for('.set_spreadsheet_breakpoint'))
    return render_template('spreadsheets/spreadsheet_columns_form.html', spreadsheet=spreadsheet, errors=errors)


@spreadsheet_blueprint.route('/set_spreadsheet_breakpoint', methods=['GET','POST'])
def set_spreadsheet_breakpoint():
    errors = []
    #spreadsheet = Spreadsheet.from_json(session['spreadsheet'])
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
    return render_template('spreadsheets/spreadsheet_breakpoint_form.html',
                                data=data.to_json(orient='values'),
                                x_values=spreadsheet.x_values,
                                x_labels=spreadsheet.x_labels,
                                x_label_values=spreadsheet.x_label_values,
                                qs=list(spreadsheet.df.nitecap_q.values),
                                ids=list(spreadsheet.df['id']),
                                column_pairs=spreadsheet.column_pairs,
                                breakpoint = spreadsheet.breakpoint)



@spreadsheet_blueprint.route('/show_spreadsheet/<int:spreadsheet_id>', methods=['GET','POST'])
def show_spreadsheet(spreadsheet_id):
    errors = []
    if 'email' not in session or not session['email']:
        flash('You must be logged in to manage your saved spreadsheets.')
        return redirect(url_for('.load_spreadsheet'))
    user = User.find_by_email(session['email'])
    spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
    if not spreadsheet:
        errors.append('You may only manage your own spreadsheets.')
        return render_template('spreadsheets/user_spreadsheets.html', user=user, errors=errors)
    if request.method == 'POST':
        row_index = int(request.form['row_index'])
        spreadsheet.breakpoint = row_index
        spreadsheet.save_to_db()
        session['spreadsheet'] = spreadsheet.to_json()
        return redirect(url_for('.display_heatmap'))

    session["spreadsheet_id"] = spreadsheet.id

    data = spreadsheet.get_raw_data()
    return render_template('spreadsheets/spreadsheet_breakpoint_form.html',
                                data=data.to_json(orient='values'),
                                x_values=spreadsheet.x_values,
                                x_labels=spreadsheet.x_labels,
                                x_label_values=spreadsheet.x_label_values,
                                qs=list(spreadsheet.df.nitecap_q.values),
                                ids=list(spreadsheet.df['id']),
                                column_pairs=spreadsheet.column_pairs,
                                breakpoint=spreadsheet.breakpoint)


@spreadsheet_blueprint.route('/heatmap', methods=['POST'])
def display_heatmap():
    # errors = []
    # # spreadsheet = Spreadsheet.from_json(session['spreadsheet'])
    # if 'spreadsheet_id' not in session or not session['spreadsheet_id']:
    #     errors.append("You may only work with your own spreadsheet.")
    #     return render_template('spreadsheets/spreadsheet_upload_form.html', errors=errors)
    # spreadsheet = Spreadsheet.find_by_id(session['spreadsheet_id'])
    # data, labels = spreadsheet.reduce_dataframe(spreadsheet.breakpoint)
    # data = spreadsheet.normalize_data(data)
    # heatmap_x_values = []
    # for day in range(spreadsheet.days):
    #     for timepoint in range(spreadsheet.timepoints):
    #         num_replicates = spreadsheet.num_replicates[timepoint]
    #         for rep in range(num_replicates):
    #             heatmap_x_values.append(f"Day{day + 1} Timepoint{timepoint + 1} Rep{rep + 1}")
    # return render_template('spreadsheets/heatmap.html',
    #                        data=data.to_json(orient='values'),
    #                        x_values=spreadsheet.x_labels,
    #                        heatmap_x_values=heatmap_x_values,
    #                        ids=labels,
    #                        column_pairs=spreadsheet.column_pairs,
    #                        timepoint_pairs=spreadsheet.timepoint_pairs)
    errors = []
    json_data = request.get_json()
    row_index = json_data.get('row_index',0)
    spreadsheet = Spreadsheet.find_by_id(session['spreadsheet_id'])
    spreadsheet.breakpoint = row_index
    spreadsheet.save_to_db()
    data, labels = spreadsheet.reduce_dataframe(spreadsheet.breakpoint)
    data = spreadsheet.normalize_data(data)
    heatmap_x_values = []
    for day in range(spreadsheet.days):
        for timepoint in range(spreadsheet.timepoints):
             num_replicates = spreadsheet.num_replicates[timepoint]
             for rep in range(num_replicates):
                 heatmap_x_values.append(f"Day{day + 1} Timepoint{timepoint + 1} Rep{rep + 1}")
    heatmap_data = data.where((pd.notnull(data)), None).values.tolist()
    return jsonify(
                        {
                            "heatmap_labels": labels,
                            "heatmap_data": heatmap_data,
                            "heatmap_x_values": heatmap_x_values
                        }
                    )



@spreadsheet_blueprint.route('/display_spreadsheets', methods=['GET'])
def display_spreadsheets():
    if 'email' not in session or not session['email']:
        flash('You must be logged in to see your saved spreadsheets.')
        return redirect(url_for('.load_spreadsheet'))
    print("Display spreadsheets {session['email']}")
    user = User.find_by_email(session['email'])
    return render_template('spreadsheets/user_spreadsheets.html', user=user)


@spreadsheet_blueprint.route('/delete/<int:spreadsheet_id>', methods=['GET'])
def delete(spreadsheet_id):
    errors = []
    if 'email' not in session or not session['email']:
        flash('You must be logged in to manage your saved spreadsheets.')
        return redirect(url_for('.load_spreadsheet'))
    user = User.find_by_email(session['email'])
    spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
    if not spreadsheet:
        errors.append('You may only manage your own spreadsheets.')
        return render_template('spreadsheets/user_spreadsheets.html', user=user, errors=errors)
    try:
        spreadsheet.delete_from_db()
        os.remove(spreadsheet.file_path)
        os.remove(spreadsheet.uploaded_file_path)
    except Exception as e:
       errors.append("The spreadsheet data may not have been all successfully removed.")
    if errors:
        return render_template('spreadsheets/user_spreadsheets.html', user=user, errors=errors)
    return redirect(url_for('.display_spreadsheets'))


@spreadsheet_blueprint.route('/download/<int:spreadsheet_id>', methods=['GET'])
def download(spreadsheet_id):
    errors = []
    if 'email' not in session or not session['email']:
        flash('You must be logged in to manage your saved spreadsheets.')
        return redirect(url_for('users.login_user'))
    user = User.find_by_email(session['email'])
    spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
    if not spreadsheet:
        errors.append('You may only manage your own spreadsheets.')
        return render_template('spreadsheets/user_spreadsheets.html', user=user, errors=errors)
    try:
        return send_file(spreadsheet.file_path, as_attachment=True, attachment_filename='processed_spreadsheet.txt')
    except Exception as e:
        errors.append("The processed spreadsheet data could not be downloaded.")
        return render_template('spreadsheets/user_spreadsheets.html', user=user, errors=errors)


@spreadsheet_blueprint.route('/edit/<int:spreadsheet_id>', methods=['GET','POST'])
def edit_details(spreadsheet_id):
    errors = []
    if 'email' not in session or not session['email']:
        flash('You must be logged in to manage your saved spreadsheets.')
        return redirect(url_for('users.login_user'))
    user = User.find_by_email(session['email'])
    spreadsheet = user.find_user_spreadsheet_by_id(spreadsheet_id)
    if not spreadsheet:
        errors.append('You may only manage your own spreadsheets.')
        return render_template('spreadsheets/user_spreadsheets.html', user=user, errors=errors)
    session['spreadsheet_id'] = spreadsheet_id
    if request.method == "POST":
        days = request.form['days']
        timepoints = request.form['timepoints']
        if not days.isdigit():
            errors.append(f"The value for days is required and must be a positve integer.")
        if not timepoints.isdigit():
            errors.append(f"The value for timepoints is required and must be a positve integer.")
        if errors:
            return render_template('spreadsheets/edit_form.html', errors=errors, days=days,
                                   timepoints=timepoints)
        spreadsheet.days = days
        spreadsheet.timepoints = timepoints
        spreadsheet.save_to_db()
        return redirect(url_for('.edit_columns'))
    return render_template('spreadsheets/edit_form.html', spreadsheet_id=spreadsheet_id,
                           days=spreadsheet.days, timepoints=spreadsheet.timepoints)


@spreadsheet_blueprint.route('/edit', methods=['GET', 'POST'])
def edit_columns():
    errors = []
    if 'email' not in session or not session['email']:
        flash('You must be logged in to manage your saved spreadsheets.')
        return redirect(url_for('users.login_user'))
    user = User.find_by_email(session['email'])
    spreadsheet = user.find_user_spreadsheet_by_id(session['spreadsheet_id'])
    if not spreadsheet:
        errors.append('You may only manage your own spreadsheets.')
        return render_template('spreadsheets/user_spreadsheets.html', user=user, errors=errors)
    if request.method == 'POST':
        column_labels = list(request.form.values())
        error, messages = spreadsheet.validate(column_labels)
        errors.extend(messages)
        if error:
            return render_template('spreadsheets/edit_columns_form.html', spreadsheet=spreadsheet, errors=errors)
        spreadsheet.identify_columns(column_labels)
        spreadsheet.compute_ordering()
        spreadsheet.save_to_db()
        return redirect(url_for('.show_spreadsheet', spreadsheet_id=spreadsheet.id))
    return render_template('spreadsheets/edit_columns_form.html', spreadsheet=spreadsheet)


