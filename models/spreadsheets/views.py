import magic
from flask import Blueprint, request, session, url_for, redirect, render_template
from models.spreadsheets.spreadsheet import Spreadsheet
from werkzeug.utils import secure_filename
import os
import constants
from util import check_number

spreadsheet_blueprint = Blueprint('spreadsheets', __name__)

@spreadsheet_blueprint.route('/load_spreadsheet', methods=['GET','POST'])
def load_spreadsheet():
    if request.method == 'POST':
        # http: // flask.pocoo.org / docs / 1.0 / patterns / fileuploads /  # improving-uploads
        days = request.form['days']
        timepoints = request.form['timepoints']
        upload_file = request.files['upload_file'] if 'upload_file' in request.files else None

        # Validate and give errors
        error = False
        messages = []

        if not check_number(days):
            messages.append(f"The value for days is required and must be a positve integer.")
            error = True
        if not check_number(timepoints):
            messages.append(f"The value for timepoints is required and must be a positve integer.")
            error = True
        if not upload_file:
            messages.append(f'No spreadsheet file was provided.')
            error = True
        else:
            if not len(upload_file.filename):
                messages.append(f'No spreadsheet file was provided.')
                error = True
            if not allowed_file(upload_file.filename):
                messages.append(f"File must be one of the following types: {', '.join(constants.ALLOWED_EXTENSIONS)}")
                error = True

            # This test appears to pass everything as text/plain
            file_mime_type = magic.from_buffer(upload_file.filename, mime=True)
            if file_mime_type not in constants.ALLOWED_MIME_TYPES:
                messages.append(f"File must be one of the following types: {', '.join(constants.ALLOWED_MIME_TYPES)}")
                error = True

        if error:
            return render_template('spreadsheets/spreadsheet_upload_form.html', messages=messages, days=days, timepoints=timepoints)

        filename = secure_filename(upload_file.filename)
        file_path = os.path.join(constants.UPLOAD_FOLDER, filename)
        upload_file.save(file_path)

        # For any files masquerading as one of the acceptable file types by virtue of its file extension, it appears we
        # can only identify it when pandas fails to parse it while creating a spreadsheet object.  We throw the file
        # away and report the error.
        try:
            spreadsheet = Spreadsheet(days, timepoints, uploaded_file_path = file_path)
        except Exception as e:
            os.remove(file_path)
            messages.append(f"The file provided is not parseable.")
            return render_template('spreadsheets/spreadsheet_upload_form.html', messages=messages, days=days, timepoints=timepoints)
        session['spreadsheet'] = spreadsheet.to_json()

        return redirect(url_for('.identify_spreadsheet_columns'))

    return render_template('spreadsheets/spreadsheet_upload_form.html', messages=[])

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in constants.ALLOWED_EXTENSIONS

@spreadsheet_blueprint.route('spreadsheets/identify_spreadsheet_columns', methods=['GET','POST'])
def identify_spreadsheet_columns():
    spreadsheet = Spreadsheet.from_json(session['spreadsheet'])
    if request.method == 'POST':
        column_labels = list(request.form.values())

        error, messages = spreadsheet.validate(column_labels)
        if error:
            return render_template('spreadsheets/spreadsheet_columns_form.html', spreadsheet=spreadsheet, messages=messages)

        spreadsheet.identify_columns(column_labels)

        spreadsheet.compute_ordering()
        session['spreadsheet'] = spreadsheet.to_json()
        return redirect(url_for('.set_spreadsheet_breakpoint'))
    return render_template('spreadsheets/spreadsheet_columns_form.html', spreadsheet=spreadsheet, messages=[])


@spreadsheet_blueprint.route('/set_spreadsheet_breakpoint', methods=['GET','POST'])
def set_spreadsheet_breakpoint():
    spreadsheet = Spreadsheet.from_json(session['spreadsheet'])
    if request.method == 'POST':
        row_index = int(request.form['row_index'])
        spreadsheet.breakpoint = row_index
        session['spreadsheet'] = spreadsheet.to_json()
        return redirect(url_for('.display_heatmap'))

    data = spreadsheet.get_raw_data()
    return render_template('spreadsheets/spreadsheet_breakpoint_form.html',
                                data=data.to_json(orient='values'),
                                x_values=spreadsheet.x_labels,
                                ids=list(spreadsheet.df['id']),
                                column_pairs=spreadsheet.column_pairs,
                                timepoint_pairs = spreadsheet.timepoint_pairs)


@spreadsheet_blueprint.route('/heatmap', methods=['GET','POST'])
def display_heatmap():
    spreadsheet = Spreadsheet.from_json(session['spreadsheet'])
    data, labels = spreadsheet.reduce_dataframe(spreadsheet.breakpoint)
    data = spreadsheet.normalize_data(data)
    heatmap_x_values = []
    for day in range(spreadsheet.days):
        for timepoint in range(spreadsheet.timepoints):
            num_replicates = spreadsheet.num_replicates[timepoint]
            for rep in range(num_replicates):
                heatmap_x_values.append(f"Day{day + 1} Timepoint{timepoint + 1} Rep{rep + 1}")
    return render_template('spreadsheets/heatmap.html',
                           data=data.to_json(orient='values'),
                           x_values=spreadsheet.x_labels,
                           heatmap_x_values=heatmap_x_values,
                           ids=labels,
                           column_pairs=spreadsheet.column_pairs,
                           timepoint_pairs=spreadsheet.timepoint_pairs)
