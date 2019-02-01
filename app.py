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

@app.route('/', methods=['POST','GET'])
def spreadsheet_details(days=None, timepoints=None):
    return render_template('spreadsheet_details.html')

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/spreadsheet_details_action', methods=['POST'])
def spreadsheet_details_action():
    #http: // flask.pocoo.org / docs / 1.0 / patterns / fileuploads /  # improving-uploads
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
        error=True

    if error:
        return spreadsheet_details()

    if upload_file and allowed_file(upload_file.filename):
        filename = secure_filename(upload_file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        upload_file.save(file_path)
        spreadsheet = Spreadsheet(days, timepoints, file_path)
        session['spreadsheet'] = spreadsheet.to_json()

    return render_template('spreadsheet_display.html', spreadsheet=spreadsheet)

@app.route('/spreadsheet_display_action', methods=['POST'])
def spreadsheet_display_action():
    spreadsheet = Spreadsheet.from_json(session['spreadsheet'])
    column_labels = list(request.form.values())


    validation = spreadsheet.validate(column_labels)
    if validation is not "okay":
        spreadsheet.column_defaults = list(zip(spreadsheet.columns, column_labels))
        return render_template("spreadsheet_display.html", spreadsheet=spreadsheet, error=validation)

    spreadsheet.identify_columns(column_labels)
    spreadsheet.compute_ordering()

    ids = list(spreadsheet.df['id'])
    data = spreadsheet.trimmed_df.to_json(orient='values')

    return render_template('spreadsheet_breakpoint.html',
                            data=data,
                            x_values=spreadsheet.x_labels,
                            ids=ids,
                            column_pairs=spreadsheet.column_pairs,
                            timepoint_pairs = spreadsheet.timepoint_pairs)


if __name__ == '__main__':
    app.run()
