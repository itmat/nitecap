import boto3
import os
import time

λ = boto3.client("lambda")
ssm = boto3.client("ssm")


def get_snapshot_lambda_name():
    response = ssm.get_parameter(Name=os.environ["SNAPSHOT_LAMBDA_NAME_PARAMETER"])
    return response["Parameter"]["Value"]

print("TRANSITION_START")
open("/nitecap_web/TRANSITION_START", "w")

time.sleep(10)

open("/nitecap_web/TRANSITION_END", "w")
print("TRANSITION_END")

while True:
    try:
        λ.invoke(FunctionName=get_snapshot_lambda_name(), InvocationType="Event")
        print("Invoked the snapshot lambda")
        break
    except (
        λ.exceptions.ResourceNotFoundException,
        λ.exceptions.ResourceNotReadyException,
    ):
        print("Waiting for the snapshot lambda to be constructed")
        time.sleep(10)
