import os

import boto3
import numpy as np
import simplejson as json

from io import BytesIO
from operator import itemgetter

from algorithms import compute
from processor import parallel_compute as parallel
from notifier import send_notification_via_websockets

s3 = boto3.resource("s3")
SPREADSHEET_BUCKET_NAME = os.environ["SPREADSHEET_BUCKET_NAME"]


def load_spreadsheet(userId, spreadsheetId, viewId):
    spreadsheet = BytesIO()
    s3.Object(
        SPREADSHEET_BUCKET_NAME,
        f"{userId}/spreadsheets/{spreadsheetId}/views/{viewId}/data",
    ).download_fileobj(spreadsheet)

    spreadsheet.seek(0)

    metadata = BytesIO()
    s3.Object(
        SPREADSHEET_BUCKET_NAME,
        f"{userId}/spreadsheets/{spreadsheetId}/views/{viewId}/metadata",
    ).download_fileobj(metadata)

    metadata.seek(0)
    metadata = json.load(metadata)

    data = np.loadtxt(spreadsheet, delimiter=",")

    return data, metadata


def handler(event, context):
    analysisId, userId, algorithm, spreadsheets = itemgetter(
        "analysisId", "userId", "algorithm", "spreadsheets"
    )(event)

    spreadsheet = spreadsheets[0]
    data, metadata = load_spreadsheet(userId, **spreadsheet)

    sample_collection_times = np.array(metadata["sample_collection_times"])

    # Sort by time
    data[:, sample_collection_times.argsort()]
    sample_collection_times.sort()

    send_notification = send_notification_via_websockets(
        {"userId": userId, "analysisId": analysisId}
    )

    parameters = (data, sample_collection_times)

    if algorithm == "jtk" and event["computeWaveProperties"]:
        period, lag, amplitude = parallel(
            compute(algorithm), *parameters, send_notification=send_notification, compute_wave_properties=True
        )
        results = json.dumps({"period": period, "lag": lag, "amplitude": amplitude}, ignore_nan=True)
    elif algorithm == "cosinor":
        x, p = parallel(
            compute(algorithm), *parameters, send_notification=send_notification
        )
        results = json.dumps({"x": x, "p": p}, ignore_nan=True)
    else:
        p = parallel(
            compute(algorithm), *parameters, send_notification=send_notification
        )
        results = json.dumps({"p": p}, ignore_nan=True)

    s3.Object(
        SPREADSHEET_BUCKET_NAME, f"{userId}/analyses/{analysisId}/results"
    ).upload_fileobj(BytesIO(results.encode()))

    send_notification({"status": "COMPLETED"})
