import boto3
import simplejson as json
from functools import wraps
import os

import pandas as pd

from flask import Blueprint, request, session
from hashlib import sha256
from io import BytesIO

from botocore.client import Config
from botocore.exceptions import ClientError

from models.shares import Share
from models.users.user import User
from models.users.decorators import ajax_requires_account, ajax_requires_account_or_share

s3 = boto3.resource("s3")
s3_client = boto3.client("s3", config=Config(s3={"addressing_style": "virtual"}))
sfn = boto3.client("stepfunctions")

ALGORITHMS = ["cosinor", "ls", "arser", "jtk", "one_way_anova"]
COMPUTATION_STATE_MACHINE_ARN = os.environ["COMPUTATION_STATE_MACHINE_ARN"]
SPREADSHEET_BUCKET_NAME = os.environ["SPREADSHEET_BUCKET_NAME"]

analysis_blueprint = Blueprint("analysis", __name__)

def analysis_require_account_or_share(func):
    '''
    Decorator to check for permissions before an endpoint

    Unlike users.decorators.ajax_requires_account_or_share, this one
    pulls the appropriate data (spreadsheet ids) from the analysisId
    '''
    @wraps(func)
    def decorated_func(analysisId, **kwargs):
        share_token = request.headers.get("Authentication", '')
        if share_token != '':
            # Share token present, check if the analysis is for the shared spreadsheets
            try:
                share = Share.find_by_id(share_token)
            except Exception as e:
                return "The URL you received does not work.  It may have been mangled in transit.  Please request another share.", 401
            sharing_user = User.find_by_id(share.user_id)
            parameters = json.loads(get_parameters(sharing_user, analysisId=analysisId))
            spreadsheetId = parameters['spreadsheetId']
            shared_spreadsheet_ids = [int(id) for id in share.spreadsheet_ids_str.split(',')]
            if spreadsheetId in shared_spreadsheet_ids:
                return func(**kwargs, analysisId=analysisId, user=sharing_user)
            else:
                return f"The URL you received does not work.  It may have been mangled in transit.  Please request another share.", 401
        else:
            # No share, just check user account in session cookie
            user = User.find_by_email(session['email'])
            if not user:
                return "You must be logged in or working on a spreadsheet to perform this activity.", 401
            parameters = json.loads(get_parameters(user, analysisId=analysisId))
            spreadsheetId = parameters['spreadsheetId']
            if user.find_user_spreadsheet_by_id(spreadsheetId) is not None:
                return func(**kwargs, analysisId=analysisId, user=user)
            else:
                return "The URL you received does not work. It may have been mangled in transit. Please request aanother share.", 401
    return decorated_func

@analysis_blueprint.route("/", methods=["post"])
@ajax_requires_account_or_share
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


@analysis_blueprint.route("/<analysisId>/results/url", methods=["get"])
@analysis_require_account_or_share
def get_results_url(user, analysisId):
    try:
        response = s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": SPREADSHEET_BUCKET_NAME,
                "Key": f"{user.id}/analyses/{analysisId}/results",
            },
        )

    except Exception as error:
        return f"Failed to generate analysis results URL: {error}", 500

    return response


@analysis_blueprint.route("/<analysisId>/parameters", methods=["get"])
# TODO: should this require authorization? For now, it's used IN authorization so it cannot
# but do we really need this as an endpoint or just a function?
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

@analysis_blueprint.route("/<analysisId>/status", methods=["get"])
@analysis_require_account_or_share
def get_analysis_status(user, analysisId):
    """
    Possible responses:
     - RUNNING
     - COMPLETED
     - FAILED - the failure is not supposed to be due to transient network errors
     - DOES_NOT_EXIST - the analysis has never been submitted, or was submitted more than 90 days ago and it failed
    """

    try:
        s3_client.head_object(
            Bucket=SPREADSHEET_BUCKET_NAME,
            Key=f"{user.id}/analyses/{analysisId}/results",
        )
        return "COMPLETED"
    except ClientError:
        try:
            executionArn = f"{COMPUTATION_STATE_MACHINE_ARN.replace('stateMachine', 'execution')}:{analysisId}"
            status = sfn.describe_execution(executionArn=executionArn)["status"]
            if status == "RUNNING":
                return "RUNNING"
            if status == "SUCCEEDED":
                return "COMPLETED"
            if status in ["FAILED", "TIMED_OUT", "ABORTED"]:
                return "FAILED"
        except sfn.exceptions.ExecutionDoesNotExist:
            return "DOES_NOT_EXIST"


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
