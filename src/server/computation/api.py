import boto3
import simplejson as json
import os

import pandas as pd

from hashlib import sha256
from io import BytesIO

from flask import request
from app import app
from models.users.decorators import ajax_requires_account, ajax_requires_account_or_share

s3 = boto3.resource("s3")
sfn = boto3.client("stepfunctions")

ALGORITHMS = ["cosinor", "ls", "arser"]
COMPUTATION_STATE_MACHINE_ARN = os.environ["COMPUTATION_STATE_MACHINE_ARN"]
SPREADSHEET_BUCKET_NAME = os.environ["SPREADSHEET_BUCKET_NAME"]


@app.route("/analysis", methods=["post"])
@ajax_requires_account
def submit_analysis(user):
    parameters = request.get_json()

    if parameters["algorithm"] not in ALGORITHMS:
        raise NotImplementedError
    if parameters["spreadsheetId"] not in [
        spreadsheet.id for spreadsheet in user.spreadsheets
    ]:
        raise KeyError

    analysis = {
        "userId": str(user.id),
        "algorithm": parameters["algorithm"],
        "spreadsheetId": parameters["spreadsheetId"],
        "version": parameters['version'],
    }

    analysisId = sha256(
        json.dumps(analysis, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()

    try:
        s3.Object(
            SPREADSHEET_BUCKET_NAME,
            f"{user.id}/analyses/{analysisId}/parameters",
        ).upload_fileobj(BytesIO(json.dumps(parameters).encode()))

        sfn.start_execution(
            stateMachineArn=COMPUTATION_STATE_MACHINE_ARN,
            name=analysisId,
            input=json.dumps({"analysisId": analysisId, **analysis}),
            traceHeader=analysisId,
        )
    except sfn.exceptions.ExecutionAlreadyExists as error:
        # Already ran/running, so we just need to let them know about it
        return analysisId
    except Exception as error:
        return f"Failed to send request to perform computations: {error}", 500

    return analysisId


@app.route("/analysis/<analysisId>/results", methods=["get"])
@ajax_requires_account
def get_results(user, analysisId):
    try:
        results = BytesIO()
        s3.Object(
            SPREADSHEET_BUCKET_NAME,
            f"{user.id}/analyses/{analysisId}/results",
        ).download_fileobj(results)

    except Exception as error:
        return f"Failed to retrieve analysis results: {error}", 500

    results.seek(0)
    return results.read()


@app.route("/analysis/<analysisId>/parameters", methods=["get"])
@ajax_requires_account
def get_parameters(user, analysisId):
    try:
        parameters = BytesIO()
        s3.Object(
            SPREADSHEET_BUCKET_NAME,
            f"{user.id}/analyses/{analysisId}/parameters",
        ).download_fileobj(parameters)

    except Exception as error:
        return f"Failed to retrieve analysis parameters: {error}", 500

    parameters.seek(0)
    return parameters.read()


def store_spreadsheet_to_s3(spreadsheet):
    data = spreadsheet.get_raw_data().to_csv(header=False, index=False)

    index, header = spreadsheet.get_raw_data().axes
    metadata = {
        "header": header.to_list(),
        "index": index.to_list(),
        "cycle_length": spreadsheet.timepoints,
        "timepoints": spreadsheet.x_values,
    }

    with open(spreadsheet.uploaded_file_path, "rb") as original:
        s3.Object(
            SPREADSHEET_BUCKET_NAME,
            f"{spreadsheet.user.id}/spreadsheets/{spreadsheet.id}/original",
        ).upload_fileobj(
            original,
            ExtraArgs={
                "Metadata": {
                    "Filename": spreadsheet.original_filename,
                }
            },
        )

    s3.Object(
        SPREADSHEET_BUCKET_NAME,
        f"{spreadsheet.user.id}/spreadsheets/{spreadsheet.id}/data",
    ).upload_fileobj(BytesIO(data.encode()))

    s3.Object(
        SPREADSHEET_BUCKET_NAME,
        f"{spreadsheet.user.id}/spreadsheets/{spreadsheet.id}/metadata",
    ).upload_fileobj(BytesIO(json.dumps(metadata).encode()))
