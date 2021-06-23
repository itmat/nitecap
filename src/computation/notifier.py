import boto3
import os
import simplejson as json

from time import sleep

NOTIFICATION_FREQUENCY = 2

CONNECTION_TABLE_NAME = os.environ["CONNECTION_TABLE_NAME"]
NOTIFICATION_API_ENDPOINT = os.environ["NOTIFICATION_API_ENDPOINT"]

db = boto3.client("dynamodb")
api = boto3.client("apigatewaymanagementapi", endpoint_url=NOTIFICATION_API_ENDPOINT)


def send_notification_via_websockets(context):
    def send_notification(message):
        user_connections = db.query(
            TableName=CONNECTION_TABLE_NAME,
            IndexName="userId-index",
            KeyConditionExpression="userId = :value",
            ExpressionAttributeValues={":value": {"S": context["userId"]}},
        )

        for connection in user_connections["Items"]:
            try:
                api.post_to_connection(
                    Data=json.dumps(
                        {"analysisId": context["analysisId"], **message}
                    ).encode(),
                    ConnectionId=connection["connectionId"]["S"],
                )
            except api.exceptions.GoneException:
                continue

    return send_notification


def notifier(processor_connection, workload_size, send_notification):
    while True:
        sleep(1 / NOTIFICATION_FREQUENCY)
        processor_connection.send("PROGRESS_UPDATE_REQUEST")
        message = processor_connection.recv()

        if message == "EXIT":
            processor_connection.close()
            break
        else:
            send_notification(
                {
                    "status": "RUNNING",
                    "progress": {"value": message, "max": workload_size},
                }
            )
