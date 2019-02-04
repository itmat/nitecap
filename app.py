import itertools

from flask import Flask, render_template, request, session, flash, redirect, url_for
from werkzeug.utils import secure_filename
import os
from models.spreadsheet import Spreadsheet

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
        upload_file = request.files['upload_file']

        # Validate and give errors
        error = False
        try:
            if int(days) < 1:
                flash("Number of days must be at least 1")
                error = True
        except ValueError:
            flash("Number of days must be an integer")
            error = True

        try:
            if int(timepoints) < 1:
                error = True
                flash("Timepoints must be at least 1")
        except ValueError:
            flash("Timepoints must be an integer")
            error = True

        if 'upload_file' not in request.files:
            flash('No file part')
            error = True
        # if user does not select file, browser also
        # submit an empty part without filename
        if upload_file.filename == '':
            flash('No selected file')
            error = True

        if not allowed_file(upload_file.filename):
            flash(f"File must be one of the following types: {', '.join(ALLOWED_EXTENSIONS)}")
            error = True

        if error:
            return load_spreadsheet()

        if upload_file and allowed_file(upload_file.filename):
            filename = secure_filename(upload_file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            upload_file.save(file_path)
            spreadsheet = Spreadsheet(days, timepoints, file_path)
            session['spreadsheet'] = spreadsheet.to_json()

        return render_template('spreadsheet_columns_form.html', spreadsheet=spreadsheet)

    return render_template('spreadsheet_upload_form.html')

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/identify_spreadsheet_columns', methods=['GET','POST'])
def identify_spreadsheet_columns():
    spreadsheet = Spreadsheet.from_json(session['spreadsheet'])
    if request.method == 'POST':
        column_labels = list(request.form.values())

        validation = spreadsheet.validate(column_labels)
        if validation is not "okay":
            spreadsheet.column_defaults = list(zip(spreadsheet.columns, column_labels))
            return render_template('spreadsheet_columns_form.html', spreadsheet=spreadsheet, error=validation)

        spreadsheet.identify_columns(column_labels)

        spreadsheet.compute_ordering()
        session['spreadsheet'] = spreadsheet.to_json()
        return render_template('spreadsheet_breakpoint_form.html',
                                data=spreadsheet.trimmed_df.to_json(orient='values'),
                                x_values=spreadsheet.x_labels,
                                ids=list(spreadsheet.df['id']),
                                column_pairs=spreadsheet.column_pairs,
                                timepoint_pairs = spreadsheet.timepoint_pairs)
    return render_template('spreadsheet_columns_form.html')

@app.route('/set_spreadsheet_breakpoint', methods=['GET','POST'])
def set_spreadsheet_breakpoint():
    spreadsheet = Spreadsheet.from_json(session['spreadsheet'])
    if request.method == 'POST':
        row_id = request.form['row_id']
        data = spreadsheet.reduce_dataframe(row_id).to_json(orient='values')
        heatmap_x_values = []
        for count, x_value in zip(spreadsheet.num_replicates, spreadsheet.x_labels):
            for item in range(count):
                heatmap_x_values.append(f"{x_value} rep {item + 1}")

        return render_template('heatmap.html',
                                data=data,
                                x_values=spreadsheet.x_labels,
                                heatmap_x_values = heatmap_x_values,
                                ids=list(spreadsheet.df['id']),
                                column_pairs=spreadsheet.column_pairs,
                                timepoint_pairs = spreadsheet.timepoint_pairs)

    return render_template('spreadsheet_breakpoint_form.html',
                                data=spreadsheet.trimmed_df.to_json(orient='values'),
                                x_values=spreadsheet.x_labels,
                                ids=list(spreadsheet.df['id']),
                                column_pairs=spreadsheet.column_pairs,
                                timepoint_pairs = spreadsheet.timepoint_pairs)


if __name__ == '__main__':
    app.run()
