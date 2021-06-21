#!/usr/bin/env python
import boto3
import datetime
import functools
import os
import pathlib
import re
import shutil
import sys
import time

sys.path.append("/var/www/flask_apps/nitecap")

print = functools.partial(print, flush=True)

import app
from db import db
from sqlalchemy.sql import text
from models.spreadsheets.spreadsheet import Spreadsheet
from models.users.user import User
from computation.api import ALGORITHMS, run, store_spreadsheet_to_s3

print(f"Updating the permissions on data folders")
for path in pathlib.Path(os.environ["UPLOAD_FOLDER"]).rglob("*"):
    shutil.chown(path, 1001, 1001)
for path in pathlib.Path(os.environ["DB_BACKUP_FOLDER"]).rglob("*"):
    shutil.chown(path, 1001, 1001)
for path in pathlib.Path(os.environ["DATABASE_FOLDER"]).rglob("*"):
    shutil.chown(path, 1001, 1001)
for path in pathlib.Path(os.environ["LOGS_DIRECTORY_PATH"]).rglob("*"):
    shutil.chown(path, 1001, 1001)

print("Cleaning up unneeded files and folders")
# These assume that the snapshot has been mounted to /nitecap_web/
shutil.rmtree("/nitecap_web/logs/")
shutil.rmtree("/nitecap_web/dbs")
shutil.rmtree("/nitecap_web/nitecap")
shutil.rmtree("/nitecap_web/disk_usage")
shutil.rmtree("/nitecap_web/backup")

db.init_app(app.app)

λ = boto3.client("lambda")
ssm = boto3.client("ssm")

WAIT_DURATION = 0.05

INACTIVE_ACCOUNT_THRESHOLD = datetime.datetime.now() - datetime.timedelta(days=32)

def transfer_spreadsheet_to_S3_and_run_analyses(spreadsheet):
    print(
        f"Transferring spreadsheet {spreadsheet.id} from user {spreadsheet.user.id} to S3"
    )
    spreadsheet.init_on_load()
    store_spreadsheet_to_s3(spreadsheet)
    del spreadsheet.df
    time.sleep(WAIT_DURATION)

    userId = str(spreadsheet.user.id)
    spreadsheetId = spreadsheet.id
    viewId = spreadsheet.edit_version

    for algorithm in ALGORITHMS:
        analysis = {
            "userId": userId,
            "algorithm": algorithm,
            "spreadsheetId": spreadsheetId,
            "viewId": viewId,
        }

        print(f"Running analysis: {analysis}")

        run(analysis)
        time.sleep(WAIT_DURATION)

with app.app.app_context():

    # First update the table schemas
    # SQLite can't modify existing tables, so we have to make copies
    # We add the autoincrement functionality to the indexes
    # and this also drops old, unused columns from spreadsheets
    update_tables = ("""
        PRAGMA foreign_keys=off;

        BEGIN TRANSACTION;

        CREATE TABLE users2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username VARCHAR(150) NOT NULL,
            email VARCHAR(150) NOT NULL,
            password VARCHAR(100) NOT NULL,
            last_access DATETIME,
            visitor BOOLEAN,
            activated BOOLEAN NOT NULL,
            UNIQUE (username),
            UNIQUE (email)
        );
        INSERT INTO users2
            SELECT *
            FROM users;
        DROP TABLE users;
        ALTER TABLE users2 RENAME TO users;

        CREATE TABLE spreadsheets2 (
            id  INTEGER PRIMARY KEY AUTOINCREMENT,
            descriptive_name VARCHAR(250) NOT NULL,
            num_timepoints INTEGER,
            timepoints INTEGER,
            repeated_measures BOOLEAN NOT NULL,
            header_row INTEGER NOT NULL,
            original_filename VARCHAR(250) NOT NULL,
            file_mime_type VARCHAR(250) NOT NULL,
            file_path VARCHAR(250),
            uploaded_file_path VARCHAR(250) NOT NULL,
            date_uploaded DATETIME NOT NULL,
            column_labels_str VARCHAR(2500),
            last_access DATETIME NOT NULL,
            ids_unique BOOLEAN NOT NULL,
            note VARCHAR(5000),
            spreadsheet_data_path VARCHAR(250),
            categorical_data VARCHAR(5000),
            user_id INTEGER NOT NULL,
            edit_version INTEGER,
            FOREIGN KEY(user_id) REFERENCES users (id)
        );
        INSERT INTO spreadsheets2
            SELECT
                id,
                descriptive_name,
                num_timepoints,
                timepoints,
                repeated_measures,
                header_row,
                original_filename,
                file_mime_type,
                file_path,
                uploaded_file_path,
                date_uploaded,
                column_labels_str,
                last_access,
                ids_unique,
                note,
                spreadsheet_data_path,
                categorical_data,
                user_id,
                edit_version
            FROM spreadsheets;
        DROP TABLE spreadsheets;
        ALTER TABLE spreadsheets2 RENAME TO spreadsheets;

        COMMIT;
        PRAGMA foreign_keys=on;
    """)

    # Run the update_tables SQL code, command-by-command
    for command in update_tables.split(";"):
        if len(command.strip()) > 0:
            db.session.execute(text(command))
    db.session.commit()

    # Update location of the spreadsheets
    print("Updating the file paths of spreadsheets")
    for spreadsheet in db.session.query(Spreadsheet).order_by(Spreadsheet.id):
        try:
            # Trim to just the file names
            if spreadsheet.file_path:
                spreadsheet.file_path = pathlib.Path(spreadsheet.file_path).name
            if spreadsheet.uploaded_file_path:
                spreadsheet.uploaded_file_path = pathlib.Path(spreadsheet.uploaded_file_path).name
                # A small number of uploaded files were erroneously recorded as being at "uploaded_spreadsheet..txt"
                # but were actually correctly stored at 'uploaded_spreadsheet.txt" and so we remove the '..' here so
                # that they can be uploaded correctly
                if '..' in spreadsheet.uploaded_file_path:
                    spreadsheet.uploaded_file_path = spreadsheet.uploaded_file_path.replace('..', '.')
            # Trim the folder path to be relative to the entire folder of uploaded data
            if spreadsheet.spreadsheet_data_path:
                _, spreadsheet_data_path_relative = re.match("(.*)(user_.*)", spreadsheet.spreadsheet_data_path).groups()
                spreadsheet.spreadsheet_data_path = spreadsheet_data_path_relative
            db.session.add(spreadsheet)
        except Exception as e:
            print(f"Error updating spreadsheet in spreadsheet {spreadsheet.id}")
            print(spreadsheet)
            raise e

    db.session.commit()

    # Now clean up visiting users too
    deleted_users = 0
    for user in db.session.query(User).order_by(User.id):
        if user.visitor and user.last_access < INACTIVE_ACCOUNT_THRESHOLD:
            print(f"Deleting visiting user {user.id}!")
            user.delete()
            deleted_users += 1

    # And remove users who never activated their account
    # who have no spreadsheets (except possibly the example shared spreadsheet
    # that used to be added to any account that clicked it)
    for user in db.session.query(User).order_by(User.id):
        if (not user.activated
            and user.last_access < INACTIVE_ACCOUNT_THRESHOLD
            and len([spreadsheet for spreadsheet in user.spreadsheet if not spreadsheet.descriptive_name.contains("Nitecap Example Data")]) == 0):

            print(f"Deleting never-activated users {user.id}")
            user.delete()
            deleted_users += 1

    print(f"Deleted a total of {deleted_users} users")
    db.session.commit()

    for spreadsheet in db.session.query(Spreadsheet).order_by(Spreadsheet.id):
        if spreadsheet.user.visitor and spreadsheet.user.last_access < INACTIVE_ACCOUNT_THRESHOLD:
            print(
                f"Deleting spreadsheet {spreadsheet.id} from user {spreadsheet.user_id} since user is visitor"
            )
            spreadsheet.delete()
            continue

        if spreadsheet.is_categorical():
            print(
                f"Skipping over spreadsheet {spreadsheet.id} from user {spreadsheet.user_id} since this is a categorical spreadsheet"
            )
            continue

        if spreadsheet.column_labels_str is None:
            print(
                f"Skipping over spreadsheet {spreadsheet.id} from user {spreadsheet.user_id} since it doesn't have column labels string"
            )
            continue

        transfer_spreadsheet_to_S3_and_run_analyses(spreadsheet)
    db.session.commit()

def get_snapshot_lambda_name():
    response = ssm.get_parameter(Name=os.environ["SNAPSHOT_LAMBDA_NAME_PARAMETER"])
    return response["Parameter"]["Value"]


while True:
    try:
        λ.invoke(FunctionName=get_snapshot_lambda_name(), InvocationType="Event")
        print("Invoked the snapshot lambda")
        break
    except (
        λ.exceptions.ResourceNotFoundException,
        λ.exceptions.ResourceNotReadyException,
    ):
        print("Waiting for the snapshot lambda to be constructed")
        time.sleep(10)
