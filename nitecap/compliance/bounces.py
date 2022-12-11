import boto3
import json
import os

dynamodb = boto3.resource("dynamodb")
ses = boto3.client("ses")

suppression_list = dynamodb.Table(os.environ["EMAIL_SUPPRESSION_LIST_NAME"])
soft_bounces_recipient = os.environ["SOFT_BOUNCES_RECIPIENT"]


def handler(event, context):
    for record in event["Records"]:
        message = json.loads(record["Sns"]["Message"])

        bounceType = message["bounce"]["bounceType"]
        bounceSubType = message["bounce"]["bounceSubType"]

        if bounceType == "Permanent" and bounceSubType in ["General", "NoEmail"]:
            for recipient in message["bounce"]["bouncedRecipients"]:
                suppression_list.put_item(Item={"email": recipient["emailAddress"]})
        else:
            ses.send_email(
                Source=recipient,
                Destination={
                    "ToAddresses": [soft_bounces_recipient],
                },
                Message={
                    "Subject": {"Data": "Bounced e-mail"},
                    "Body": {"Text": {"Data": json.dumps(message, indent=4)}},
                },
            )
