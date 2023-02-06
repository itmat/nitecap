import boto3
import os
import simplejson as json

from hashlib import sha256
from io import BytesIO

from flask import Blueprint, request

from botocore.client import Config
from botocore.exceptions import ClientError

from computation.utils import get_analysis_parameters
from models.users.decorators import ajax_requires_account_or_share
from models.spreadsheets.spreadsheet import Spreadsheet

s3 = boto3.resource("s3")
s3_client = boto3.client("s3", config=Config(s3={"addressing_style": "virtual"}))
sfn = boto3.client("stepfunctions")

ALGORITHMS = ["cosinor", "differential_cosinor", "ls", "arser", "jtk", "one_way_anova", "two_way_anova", "rain", "upside"]
COMPUTATION_STATE_MACHINE_ARN = os.environ["COMPUTATION_STATE_MACHINE_ARN"]
SPREADSHEET_BUCKET_NAME = os.environ["SPREADSHEET_BUCKET_NAME"]

environment = os.environ["ENV"]

analysis_blueprint = Blueprint("analysis", __name__)


def run(analysis):
    analysisId = sha256(
        json.dumps(analysis, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()

    try:
        s3.Object(
            SPREADSHEET_BUCKET_NAME,
            f"{analysis['userId']}/analyses/{analysisId}/parameters",
        ).upload_fileobj(
            BytesIO(json.dumps({"analysisId": analysisId, **analysis}).encode())
        )

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


@analysis_blueprint.route("/", methods=["post"])
@ajax_requires_account_or_share
def submit_analysis(user):
    parameters = request.get_json()

    if parameters["algorithm"] not in ALGORITHMS:
        raise NotImplementedError

    user_spreadsheets = [spreadsheet.id for spreadsheet in user.spreadsheets]

    for spreadsheet in parameters["spreadsheets"]:
        if spreadsheet["spreadsheetId"] not in user_spreadsheets:
            raise KeyError

        currentViewId = Spreadsheet.find_by_id(spreadsheet["spreadsheetId"]).edit_version
        if not 0 <= spreadsheet["viewId"] <= currentViewId:
            raise KeyError

    compute_wave_properties = parameters.get("computeWaveProperties", False)
    if not isinstance(compute_wave_properties, bool):
        raise ValueError

    analysis = {
        "userId": user.id,
        "algorithm": parameters["algorithm"],
        "spreadsheets": parameters["spreadsheets"],
        "computeWaveProperties": compute_wave_properties,
    }

    if environment == "DEV":
        analysis.update(**parameters)

    return run(analysis)


@analysis_blueprint.route("/<analysisId>/results/url", methods=["get"])
@ajax_requires_account_or_share
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
@ajax_requires_account_or_share
def get_parameters(user, analysisId):
    try:
        return get_analysis_parameters(user.id, analysisId)
    except Exception as error:
        return f"Failed to retrieve analysis parameters: {error}", 500


@analysis_blueprint.route("/<analysisId>/status", methods=["get"])
@ajax_requires_account_or_share
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
    data = spreadsheet.get_raw_data().to_csv(header=False, index=False, na_rep="nan")

    with open(spreadsheet.get_uploaded_file_path(), "rb") as original:
        s3.Object(
            SPREADSHEET_BUCKET_NAME,
            f"{spreadsheet.user.id}/spreadsheets/{spreadsheet.id}/original",
        ).upload_fileobj(original)

    cycle_length = 24

    metadata = {
        "cycle_length": cycle_length,
        "index": spreadsheet.get_ids(),
        "sample_collection_times": [
            t * cycle_length / spreadsheet.timepoints for t in spreadsheet.x_values
        ],
        "submitted_file_name": spreadsheet.original_filename,
    }

    viewId = spreadsheet.edit_version

    s3.Object(
        SPREADSHEET_BUCKET_NAME,
        f"{spreadsheet.user.id}/spreadsheets/{spreadsheet.id}/views/{viewId}/data",
    ).upload_fileobj(BytesIO(data.encode()))

    s3.Object(
        SPREADSHEET_BUCKET_NAME,
        f"{spreadsheet.user.id}/spreadsheets/{spreadsheet.id}/views/{viewId}/metadata",
    ).upload_fileobj(BytesIO(json.dumps(metadata).encode()))
