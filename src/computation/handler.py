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


def bh(P):
    """Benjamini-Hochberg FDR control"""

    P = np.array(P)
    (indices_of_finite_values,) = np.where(np.isfinite(P))

    p = P[indices_of_finite_values]

    sort_order = np.argsort(p)

    q = np.empty(p.size)
    q[sort_order] = p[sort_order] * p.size / np.arange(1, p.size + 1)

    running_minimum = 1
    for i in reversed(sort_order):
        q[i] = running_minimum = min(q[i], running_minimum)

    Q = np.full(P.size, np.nan)
    Q.put(indices_of_finite_values, q)

    return Q


def handler(event, context):
    analysisId, userId, spreadsheetId, viewId, algorithm = itemgetter(
        "analysisId", "userId", "spreadsheetId", "viewId", "algorithm"
    )(event)

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
    sample_collection_times = np.array(metadata["sample_collection_times"])

    # Sort by time
    data[:, sample_collection_times.argsort()]
    sample_collection_times.sort()

    send_notification = send_notification_via_websockets(
        {"userId": userId, "analysisId": analysisId}
    )

    parameters = (data, sample_collection_times)

    if algorithm == "jtk" and event["computeWaveProperties"]:
        amplitude, lag, period = parallel(
            compute(algorithm), *parameters, send_notification=send_notification, compute_wave_properties=True
        )
        results = json.dumps({"amplitude": amplitude, "lag": lag, "period": period}, ignore_nan=True)
    elif algorithm == "cosinor":
        x, p = parallel(
            compute(algorithm), *parameters, send_notification=send_notification
        )
        q = bh(p).tolist()
        results = json.dumps({"x": x, "p": p, "q": q}, ignore_nan=True)
    else:
        p = parallel(
            compute(algorithm), *parameters, send_notification=send_notification
        )
        q = bh(p).tolist()
        results = json.dumps({"p": p, "q": q}, ignore_nan=True)

    s3.Object(
        SPREADSHEET_BUCKET_NAME, f"{userId}/analyses/{analysisId}/results"
    ).upload_fileobj(BytesIO(results.encode()))

    send_notification({"status": "COMPLETED"})
