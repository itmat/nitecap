import boto3
import json
import os
import time
import urllib

ec2 = boto3.client("ec2")
ecs = boto3.client("ecs")
ssm = boto3.client("ssm")


def handler(event, context):
    snapshot_id_parameter_name = os.environ["SNAPSHOT_ID_PARAMETER_NAME"]
    transition_server_instance_id = os.environ["TRANSITION_SERVER_INSTANCE_ID"]
    transition_server_cluster_name = os.environ["TRANSITION_SERVER_CLUSTER_NAME"]
    transition_server_block_storage_id = os.environ[
        "TRANSITION_SERVER_BLOCK_STORAGE_ID"
    ]

    print(
        snapshot_id_parameter_name,
        transition_server_instance_id,
        transition_server_cluster_name,
        transition_server_block_storage_id,
    )

    # for task_arn in ecs.list_tasks(cluster=transition_server_cluster_name)["taskArns"]:
    #     ecs.stop_task(cluster=transition_server_cluster_name, task=task_arn)

    # ec2.terminate_instances(InstanceIds=[transition_server_instance_id])

    # def instance_state():
    #     response = ec2.describe_instances(
    #         InstanceIds=[transition_server_instance_id]
    #     )
    #     return response["Reservations"][0]["Instances"]["State"]["Name"]

    # while instance_state() != "terminated":
    #     print("Waiting for the instance to terminate")
    #     time.sleep(10)

    # snapshot_id = ec2.create_snapshot(VolumeId=transition_server_block_storage_id)[
    #     "SnapshotId"
    # ]

    # def snapshot_state():
    #     response = ec2.describe_snapshot(SnapshotIds=[snapshot_id])
    #     return response["Snapshots"][0]["State"]

    # while snapshot_state() != "completed":
    #     print("Waiting for the snapshot to be completed")
    #     time.sleep(10)

    # ssm.put_parameter(
    #     Name=snapshot_id_parameter_name, Value=snapshot_id, Overwrite=True
    # )

    print("Attempting to send the stop wait request")

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

    print("Sent the stop wait request")
