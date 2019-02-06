import itertools

from flask import Flask, render_template, request, session, flash, redirect, url_for
from werkzeug.utils import secure_filename
import os
from models.spreadsheet import Spreadsheet
import pandas as pd
from util import check_number

import nitecap

UPLOAD_FOLDER = '/tmp/uploads'
ALLOWED_EXTENSIONS = set(['txt', 'csv', 'xlsx'])

app = Flask(__name__)
app.secret_key = 'cris'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.debug = True


@app.route('/', methods=['GET'])
def home():
    return redirect(url_for('.load_spreadsheet'))

@app.route('/load_spreadsheet', methods=['POST','GET'])
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
                messages.append(f"File must be one of the following types: {', '.join(ALLOWED_EXTENSIONS)}")
                error = True
        if error:
            return render_template('spreadsheet_upload_form.html', messages=messages, days=days, timepoints=timepoints)

        filename = secure_filename(upload_file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        upload_file.save(file_path)
        spreadsheet = Spreadsheet(days, timepoints, uploaded_file_path = file_path)
        session['spreadsheet'] = spreadsheet.to_json()

        return redirect(url_for('.identify_spreadsheet_columns'))

    return render_template('spreadsheet_upload_form.html', messages=[])

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/identify_spreadsheet_columns', methods=['GET','POST'])
def identify_spreadsheet_columns():
    spreadsheet = Spreadsheet.from_json(session['spreadsheet'])
    if request.method == 'POST':
        column_labels = list(request.form.values())

        error, messages = spreadsheet.validate(column_labels)
        if error:
            return render_template('spreadsheet_columns_form.html', spreadsheet=spreadsheet, messages=messages)

        spreadsheet.identify_columns(column_labels)

        spreadsheet.compute_ordering()
        session['spreadsheet'] = spreadsheet.to_json()
        return redirect(url_for('.set_spreadsheet_breakpoint'))
    return render_template('spreadsheet_columns_form.html', spreadsheet=spreadsheet, messages=[])

@app.route('/set_spreadsheet_breakpoint', methods=['GET','POST'])
def set_spreadsheet_breakpoint():
    spreadsheet = Spreadsheet.from_json(session['spreadsheet'])
    if request.method == 'POST':
        row_index = int(request.form['row_index'])
        spreadsheet.breakpoint = row_index
        session['spreadsheet'] = spreadsheet.to_json()
        return redirect(url_for('.display_heatmap'))

    data = spreadsheet.get_raw_data()
    return render_template('spreadsheet_breakpoint_form.html',
                                data=data.to_json(orient='values'),
                                x_values=spreadsheet.x_labels,
                                ids=list(spreadsheet.df['id']),
                                column_pairs=spreadsheet.column_pairs,
                                timepoint_pairs = spreadsheet.timepoint_pairs)


@app.route('/heatmap', methods=['GET','POST'])
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
    return render_template('/heatmap.html',
                           data=data.to_json(orient='values'),
                           x_values=spreadsheet.x_labels,
                           heatmap_x_values=heatmap_x_values,
                           ids=labels,
                           column_pairs=spreadsheet.column_pairs,
                           timepoint_pairs=spreadsheet.timepoint_pairs)



if __name__ == '__main__':
    app.run()
