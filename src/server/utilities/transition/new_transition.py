#!/usr/bin/env python
import datetime
import functools
import sys

from pathlib import Path

sys.path.append("/var/www/flask_apps/nitecap")

print = functools.partial(print, flush=True)

import app
from db import db
from sqlalchemy.sql import text
from models.spreadsheets.spreadsheet import Spreadsheet
from models.users.user import User
from models.shares import Share

  #######  

import boto3
import os
import time

from computation.api import ALGORITHMS, run, store_spreadsheet_to_s3

WAIT_DURATION = 0.01

λ = boto3.client("lambda")
ssm = boto3.client("ssm")


def run_analyses(spreadsheet):
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


def transfer_spreadsheet_to_S3(spreadsheet):
    print(
        f"Transferring spreadsheet {spreadsheet.id} from user {spreadsheet.user.id} to S3"
    )

    spreadsheet.init_on_load()
    store_spreadsheet_to_s3(spreadsheet)

    del spreadsheet.df
    time.sleep(WAIT_DURATION)


def get_snapshot_lambda_name():
    response = ssm.get_parameter(Name=os.environ["SNAPSHOT_LAMBDA_NAME_PARAMETER"])
    return response["Parameter"]["Value"]

  #######  

DRY_RUN = False

db.init_app(app.app)

INACTIVE_ACCOUNT_THRESHOLD = datetime.datetime.now() - datetime.timedelta(days=32)

with app.app.app_context():

    # First update the table schemas
    # SQLite can't modify existing tables, so we have to make copies
    # We add the autoincrement functionality to the indexes
    # and this also drops old, unused columns from spreadsheets
    update_tables = ("""
        BEGIN TRANSACTION;

        DROP TABLE IF EXISTS jobs;
        DROP TABLE IF EXISTS confirmations;

        COMMIT;
    """)

    print("Dropping specified users")
    with open(Path(__file__).parent / "users_to_delete.txt") as users_to_delete:
        user_emails = [line.strip() for line in users_to_delete.readlines()]
        for email in user_emails:
            user = User.find_by_email(email)
            if user:
                print(f"Deleting user {user.id} {user.email}")
                if not DRY_RUN:
                    user.delete()

    print("Updating the tables")
    # Run the update_tables SQL code, command-by-command
    for command in update_tables.split(";"):
        if len(command.strip()) > 0:
            db.session.execute(text(command))
    db.session.commit()

    print("Checking for spreadsheets db entries without an associated spreadsheet file")
    bad_spreadsheets = []
    for spreadsheet in db.session.query(Spreadsheet).order_by(Spreadsheet.id):
        try:
            # Trim to just the file names
            if not spreadsheet.file_path:
                bad_spreadsheets.append(spreadsheet)
                continue
            fp = spreadsheet.get_processed_file_path()
            if not fp.exists():
                bad_spreadsheets.append(spreadsheet)
                continue

            uploaded_file_path = spreadsheet.get_uploaded_file_path()
            if not uploaded_file_path.exists():
                print(f"WARNING: failed to find uploaded file for {spreadsheet.id} at {uploaded_file_path}")
        except Exception as e:
            print(f"Error checking spreadsheet in spreadsheet {spreadsheet.id}")
            print(spreadsheet)
            raise e
    print(f"Identified {len(bad_spreadsheets)} spreadsheets which are missing their associated files")
    for spreadsheet in bad_spreadsheets:
        print(f"Deleting spreadsheet {spreadsheet.id} - no associated file")
        if not DRY_RUN:
            spreadsheet.delete()

    # Now clean up visiting users too
    deleted_users = 0
    for user in db.session.query(User).order_by(User.id):
        if user.visitor and user.last_access < INACTIVE_ACCOUNT_THRESHOLD:
            print(f"Deleting visiting user {user.id}!")
            if not DRY_RUN:
                user.delete()
            deleted_users += 1

    # And remove users who never activated their account
    # who have no spreadsheets (except possibly the example shared spreadsheet
    # that used to be added to any account that clicked it)
    for user in db.session.query(User).order_by(User.id):
        if (not user.activated
            and user.last_access < INACTIVE_ACCOUNT_THRESHOLD
            and len([spreadsheet for spreadsheet in user.spreadsheet if not ("Nitecap Example Data" in spreadsheet.descriptive_name)]) == 0):

            print(f"Deleting never-activated users {user.id}")
            if not DRY_RUN:
                user.delete()
            deleted_users += 1

    print(f"Deleted a total of {deleted_users} users")
    db.session.commit()

    print("Verifying integrity of the tables")
    for spreadsheet in db.session.query(Spreadsheet).order_by(Spreadsheet.id):
        if spreadsheet.user is None:
            print(f"Spreadsheet {spreadsheet.id} has no valid user ({spreadsheet.user_id}), deleting.")
            if not DRY_RUN:
                spreadsheet.delete()
    
    command = 'SELECT file_path FROM spreadsheets WHERE file_path LIKE "/%";'
    result = list(db.session.execute(text(command)))
    print(f"Found {len(result)} spreadsheets with an absolute file_path")

    bad_shares = []
    for share in db.session.query(Share).order_by(Share.id):
        spreadsheets = [int(x) for x in share.spreadsheet_ids_str.split(',')]
        for id in spreadsheets:
            spreadsheet = Spreadsheet.find_by_id(id)
            if spreadsheet is None:
                bad_shares.append(share)
                if not DRY_RUN:
                    share.delete()
                print(f"Removing share {share.id} missing corresponding spreadsheet {id} (possibly spreadsheet was deleted)")
                continue

    db.session.commit()

    print("Upload the spreadsheets to the S3 bucket")
    for spreadsheet in db.session.query(Spreadsheet).order_by(Spreadsheet.id):
        transfer_spreadsheet_to_S3(spreadsheet)

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
