import boto3
import os
import simplejson as json

from io import BytesIO

ANALYTICS_BUCKET_NAME = os.environ["ANALYTICS_BUCKET_NAME"]

s3 = boto3.resource("s3")


def get_analysis_parameters(userId, analysisId):
    parameters = BytesIO()
    s3.Object(
        ANALYTICS_BUCKET_NAME,
        f"{userId}/analyses/{analysisId}/parameters",
    ).download_fileobj(parameters)

    parameters.seek(0)
    return parameters.read()


def get_spreadsheets_associated_with_analysis(userId, analysisId):
    parameters = json.loads(get_analysis_parameters(userId, analysisId))

    return parameters["spreadsheets"]
