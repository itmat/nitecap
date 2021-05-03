import os

import boto3
import numpy as np
import simplejson as json

from io import BytesIO
from operator import itemgetter
from statsmodels.stats.multitest import multipletests

from algorithms import compute
from processor import parallel_compute as parallel
from notifier import send_notification_via_websockets

s3 = boto3.resource("s3")
SPREADSHEET_BUCKET_NAME = os.environ["SPREADSHEET_BUCKET_NAME"]


def handler(event, context):
    analysisId, userId, spreadsheetId, algorithm = itemgetter(
        "analysisId", "userId", "spreadsheetId", "algorithm"
    )(event)

    spreadsheet = BytesIO()
    s3.Object(
        SPREADSHEET_BUCKET_NAME,
        f"{userId}/spreadsheets/{spreadsheetId}/data",
    ).download_fileobj(spreadsheet)

    spreadsheet.seek(0)

    metadata = BytesIO()
    s3.Object(
        SPREADSHEET_BUCKET_NAME,
        f"{userId}/spreadsheets/{spreadsheetId}/metadata",
    ).download_fileobj(metadata)

    metadata.seek(0)
    metadata = json.load(metadata)

    data = np.loadtxt(spreadsheet, delimiter=",")
    timepoints = np.array(metadata["timepoints"])

    send_notification = send_notification_via_websockets(
        {"userId": userId, "analysisId": analysisId}
    )

    if algorithm == "cosinor":
        x, p = parallel(
            compute(algorithm), data, timepoints, send_notification=send_notification
        )
        q = multipletests(p, method="fdr_bh")[1].tolist()
        results = json.dumps({"x": x, "p": p, "q": q}, ignore_nan=True)

    if algorithm == "ls":
        p = parallel(
            compute(algorithm), data, timepoints, send_notification=send_notification
        )
        q = multipletests(p, method="fdr_bh")[1].tolist()
        results = json.dumps({"p": p, "q": q}, ignore_nan=True)

    if algorithm == "arser":
        timepoints = np.array([0, 24, 48, 4, 28, 52, 8, 32, 56, 12, 36, 60, 16, 40, 64, 20, 44, 68])

        #timepoints = np.concatenate((timepoints, 72 + timepoints, 2*72 + timepoints, 3*72 + timepoints))
        #data = np.concatenate((data, data, data, data), axis=1)

        # Sort by timepoints
        data[:, timepoints.argsort()]
        timepoints.sort()

        p = parallel(
            compute(algorithm), data, timepoints, send_notification=send_notification
        )
        q = multipletests(p, method="fdr_bh")[1].tolist()
        results = json.dumps({"p": p, "q": q}, ignore_nan=True)

    s3.Object(
        SPREADSHEET_BUCKET_NAME, f"{userId}/analyses/{analysisId}/results"
    ).upload_fileobj(BytesIO(results.encode()))

    send_notification({"status": "COMPLETED"})
