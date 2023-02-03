import aws_cdk as cdk
import aws_cdk.custom_resources as cr
import aws_cdk.aws_ecs as ecs
import aws_cdk.aws_iam as iam

from dataclasses import dataclass


@dataclass
class ContainerInstance:
    instance_id: str
    volume_id: str


def describe_container_instance(cluster: ecs.Cluster):
    stack = cluster.stack

    cluster_container_instances_list = cr.AwsCustomResource(
        stack,
        "ClusterContainerInstancesList",
        policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
            resources=[cluster.cluster_arn]
        ),
        on_update=cr.AwsSdkCall(
            service="ECS",
            action="listContainerInstances",
            parameters={"cluster": cluster.cluster_arn},
            physical_resource_id=cr.PhysicalResourceId.of(
                cluster.autoscaling_group.auto_scaling_group_arn
            ),
        ),
        install_latest_aws_sdk=False,
    )

    cluster_container_instances_list.node.add_dependency(cluster)

    container_instance_arn = cluster_container_instances_list.get_response_field(
        "containerInstanceArns.0"
    )

    cluster_container_instances_descriptions = cr.AwsCustomResource(
        stack,
        "ClusterContainerInstancesDescriptions",
        policy=cr.AwsCustomResourcePolicy.from_sdk_calls(resources=["*"]),
        on_update=cr.AwsSdkCall(
            service="ECS",
            action="describeContainerInstances",
            parameters={
                "cluster": cluster.cluster_arn,
                "containerInstances": [container_instance_arn],
            },
            physical_resource_id=cr.PhysicalResourceId.of(container_instance_arn),
            output_paths=["containerInstances.0.ec2InstanceId"],
        ),
        install_latest_aws_sdk=False,
    )

    container_instance_id = cluster_container_instances_descriptions.get_response_field(
        "containerInstances.0.ec2InstanceId"
    )

    ec2_instances_descriptions = cr.AwsCustomResource(
        stack,
        "Ec2InstancesDescriptions",
        policy=cr.AwsCustomResourcePolicy.from_sdk_calls(resources=["*"]),
        on_update=cr.AwsSdkCall(
            service="EC2",
            action="describeInstances",
            parameters={"InstanceIds": [container_instance_id]},
            physical_resource_id=cr.PhysicalResourceId.of(container_instance_arn),
            output_paths=[
                "Reservations.0.Instances.0.BlockDeviceMappings.1.Ebs.VolumeId"
            ],
        ),
        install_latest_aws_sdk=False,
    )

    container_instance_volume_id = ec2_instances_descriptions.get_response_field(
        "Reservations.0.Instances.0.BlockDeviceMappings.1.Ebs.VolumeId"
    )

    return ContainerInstance(
        instance_id=container_instance_id, volume_id=container_instance_volume_id
    )
