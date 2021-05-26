#!/usr/bin/env python
import boto3
import os
import sys
import time

sys.path.append("/var/www/flask_apps/nitecap")
environment = "production" if os.environ.get("ENV", "PROD") == "PROD" else "development"

import app
from db import db
from models.spreadsheets.spreadsheet import Spreadsheet
from computation.api import ALGORITHMS, run, store_spreadsheet_to_s3

db.init_app(app.app)
log = app.logger.info

WAIT_DURATION = 0.25

λ = boto3.client("lambda")
SNAPSHOT_LAMBDA_NAME = os.environ["SNAPSHOT_LAMBDA_NAME"]


def transfer_spreadsheet_to_S3_and_run_analyses(spreadsheet):
    store_spreadsheet_to_s3(spreadsheet)

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

        log(f"Running analysis: {analysis}")

        if environment == "production":
            run(analysis)
            time.sleep(WAIT_DURATION)


with app.app.app_context():
    for spreadsheet in db.session.query(Spreadsheet).order_by(Spreadsheet.id):
        if spreadsheet.user.visitor:
            log(
                f"Skipping over spreadsheet {spreadsheet.id} from user {spreadsheet.user_id} since user is visitor"
            )
            continue

        transfer_spreadsheet_to_S3_and_run_analyses(spreadsheet)

log("Activating snapshot taking function")
if environment == "production":
    λ.invoke(FunctionName=SNAPSHOT_LAMBDA_NAME, InvocationType="Event")

log("Exiting")
