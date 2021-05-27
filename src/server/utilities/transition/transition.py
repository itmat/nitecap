#!/usr/bin/env python
import boto3
import os
import sys
import time

sys.path.append("/var/www/flask_apps/nitecap")

import app
from db import db
from models.spreadsheets.spreadsheet import Spreadsheet
from computation.api import ALGORITHMS, run, store_spreadsheet_to_s3

db.init_app(app.app)

λ = boto3.client("lambda")
ssm = boto3.client("ssm")

WAIT_DURATION = 0.25


def transfer_spreadsheet_to_S3_and_run_analyses(spreadsheet):
    print(
        f"Transferring spreadsheet {spreadsheet.id} from user {spreadsheet.user.id} to S3"
    )
    # spreadsheet.init_on_load()
    # store_spreadsheet_to_s3(spreadsheet)
    # time.sleep(WAIT_DURATION)

    userId = spreadsheet.user.id
    spreadsheetId = spreadsheet.id
    viewId = spreadsheet.edit_version

    for algorithm in ALGORITHMS:
        analysis = {
            "userId": userId,
            "algorithm": algorithm,
            "spreadsheetId": spreadsheetId,
            "viewId": viewId,
        }

        # print(f"Running analysis: {analysis}")

        # run(analysis)
        # time.sleep(WAIT_DURATION)


with app.app.app_context():
    for spreadsheet in db.session.query(Spreadsheet).order_by(Spreadsheet.id):
        if spreadsheet.user.visitor:
            print(
                f"Skipping over spreadsheet {spreadsheet.id} from user {spreadsheet.user_id} since user is visitor"
            )
            continue

        if spreadsheet.column_labels_str is None:
            print(
                f"Skipping over spreadsheet {spreadsheet.id} from user {spreadsheet.user_id} since it doesn't have column labels string"
            )
            continue

        transfer_spreadsheet_to_S3_and_run_analyses(spreadsheet)


def get_snapshot_lambda_name():
    response = ssm.get_parameter(Name=os.environ["SNAPSHOT_LAMBDA_NAME_PARAMETER"])
    return response["Parameter"]["Value"]


while True:
    try:
        λ.invoke(FunctionName=get_snapshot_lambda_name(), InvocationType="Event")
        break
    except (
        λ.exceptions.ResourceNotFoundException,
        λ.exceptions.ResourceNotReadyException,
    ):
        print("Waiting for the snapshot lambda to be constructed")
        time.sleep(10)
