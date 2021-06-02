import boto3
import json
import os
import time
import urllib

ec2 = boto3.client("ec2")
ecs = boto3.client("ecs")
ssm = boto3.client("ssm")

WAIT_DURATION = 10

def handler(event, context):
    snapshot_id_parameter_name = os.environ["SNAPSHOT_ID_PARAMETER_NAME"]
    transition_server_instance_id = os.environ["TRANSITION_SERVER_INSTANCE_ID"]
    transition_server_block_storage_id = os.environ[
        "TRANSITION_SERVER_BLOCK_STORAGE_ID"
    ]

    print(f"Waiting for {WAIT_DURATION} seconds")
    time.sleep(WAIT_DURATION)


    print("Terminating the instance")

    ec2.terminate_instances(InstanceIds=[transition_server_instance_id])

    def instance_state():
        response = ec2.describe_instances(InstanceIds=[transition_server_instance_id])
        return response["Reservations"][0]["Instances"][0]["State"]["Name"]

    while instance_state() != "terminated":
        print("Waiting for the instance to terminate")
        time.sleep(WAIT_DURATION)


    print("Creating snapshot")

    snapshot_id = ec2.create_snapshot(VolumeId=transition_server_block_storage_id)[
        "SnapshotId"
    ]

    def snapshot_state():
        response = ec2.describe_snapshots(SnapshotIds=[snapshot_id])
        return response["Snapshots"][0]["State"]

    while snapshot_state() != "completed":
        print("Waiting for the snapshot to be completed")
        time.sleep(WAIT_DURATION)


    print("Storing the snapshot ID")

    ssm.put_parameter(
        Name=snapshot_id_parameter_name, Value=snapshot_id, Overwrite=True
    )


    print("Sending the stop wait request")

    wait_condition_handle_url = os.environ["WAIT_CONDITION_HANDLE_URL"]

    request = urllib.request.Request(
        wait_condition_handle_url,
        headers={"Content-Type": ""},
        data=json.dumps(
            {
                "Status": "SUCCESS",
                "UniqueId": "1",
                "Data": "N/A",
                "Reason": "Snapshot was taken successfully",
            }
        ).encode(),
        method="PUT",
    )

    urllib.request.urlopen(request)


    print("Completed")
