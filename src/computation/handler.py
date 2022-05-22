import os

import boto3
import numpy as np
import simplejson as json

from collections import defaultdict
from dataclasses import dataclass
from io import BytesIO
from operator import itemgetter

from algorithms import COMPARISON_ALGORITHMS, compute
from processor import parallel_compute as parallel
from notifier import send_notification_via_websockets

s3 = boto3.resource("s3")
SPREADSHEET_BUCKET_NAME = os.environ["SPREADSHEET_BUCKET_NAME"]


@dataclass
class Spreadsheet:
    data: np.ndarray
    metadata: dict


def load_spreadsheet(userId, spreadsheetId, viewId):
    data = BytesIO()
    s3.Object(
        SPREADSHEET_BUCKET_NAME,
        f"{userId}/spreadsheets/{spreadsheetId}/views/{viewId}/data",
    ).download_fileobj(data)

    data.seek(0)

    metadata = BytesIO()
    s3.Object(
        SPREADSHEET_BUCKET_NAME,
        f"{userId}/spreadsheets/{spreadsheetId}/views/{viewId}/metadata",
    ).download_fileobj(metadata)

    metadata.seek(0)
    metadata = json.load(metadata)

    data = np.loadtxt(data, delimiter=",", ndmin=2)
    metadata["sample_collection_times"] = np.array(metadata["sample_collection_times"])

    return Spreadsheet(data, metadata)


def sort_by_time(spreadsheet):
    spreadsheet.data = spreadsheet.data[:, spreadsheet.metadata["sample_collection_times"].argsort()]
    spreadsheet.metadata["sample_collection_times"].sort()

    return spreadsheet


def handler(event, context):
    analysisId, userId, algorithm = itemgetter(
        "analysisId", "userId", "algorithm"
    )(event)

    spreadsheets = [
        sort_by_time(load_spreadsheet(userId, **spreadsheet))
        for spreadsheet in event["spreadsheets"]
    ]

    send_notification = send_notification_via_websockets(
        {"userId": userId, "analysisId": analysisId}
    )

    if algorithm in COMPARISON_ALGORITHMS:
        sample_collection_times = [spreadsheet.metadata["sample_collection_times"] for spreadsheet in spreadsheets]

        merged_labels = sorted(set.intersection(
            *(set(spreadsheet.metadata["index"]) for spreadsheet in spreadsheets)
        ))

        indexes = []
        for spreadsheet in spreadsheets:
            labels_to_indices = defaultdict(list)
            for index, label in enumerate(spreadsheet.metadata["index"]):
                labels_to_indices[label].append(index)

            indexes.append([min(labels_to_indices[label]) for label in merged_labels])

        parameters = (
            [spreadsheet.data[index, :] for spreadsheet, index in zip(spreadsheets, indexes)],
            sample_collection_times
        )

        if algorithm == "differential_cosinor":
            p_amplitude, p_phase = parallel(
                compute(algorithm), *parameters, send_notification=send_notification
            )

            results = json.dumps({"indexes": indexes, "p_amplitude": p_amplitude, "p_phase": p_phase}, ignore_nan=True)
        elif algorithm == "two_way_anova":
            p_interaction, p_main_effect = parallel(
                compute(algorithm), *parameters, send_notification=send_notification
            )

            results = json.dumps({"indexes": indexes, "p_interaction": p_interaction, "p_main_effect": p_main_effect}, ignore_nan=True)
        else:
            p = parallel(
                compute(algorithm), *parameters, send_notification=send_notification
            )

            results = json.dumps({"indexes": indexes, "p": p}, ignore_nan=True)
    else:
        spreadsheet = spreadsheets.pop()
        sample_collection_times = spreadsheet.metadata["sample_collection_times"]

        parameters = (spreadsheet.data, sample_collection_times)

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
