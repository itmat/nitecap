import aws_cdk as cdk
import aws_cdk.aws_iam as iam
import aws_cdk.aws_ecs as ecs
import aws_cdk.aws_logs as logs

from ..configuration import Configuration


def setup_logging(cluster: ecs.Cluster, configuration: Configuration):
    stack = cluster.stack

    if configuration.production:
        removal_policy = cdk.RemovalPolicy.RETAIN
    else:
        removal_policy = cdk.RemovalPolicy.DESTROY

    logs_configuration = {
        "retention": logs.RetentionDays.INFINITE,
        "removal_policy": removal_policy,
    }

    log_groups = {
        "ERROR": logs.LogGroup(stack, "ServerErrorLogGroup", **logs_configuration),
        "ACCESS": logs.LogGroup(stack, "ServerAccessLogGroup", **logs_configuration),
        "APPLICATION": logs.LogGroup(
            stack, "ServerApplicationLogGroup", **logs_configuration
        ),
    }

    logging_task = ecs.Ec2TaskDefinition(
        stack,
        "LoggingTask",
        task_role=iam.Role(
            stack,
            "LoggingRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "CloudWatchAgentServerPolicy"
                )
            ],
        ),
        volumes=[
            ecs.Volume(
                name="ServerVolume",
                host=ecs.Host(
                    source_path=configuration.server.storage.device_mount_point
                ),
            )
        ],
    )

    logging_container = logging_task.add_container(
        "LoggingContainer",
        image=ecs.ContainerImage.from_asset("nitecap/server/utilities/logging"),
        memory_limit_mib=256,
        environment={
            "LOGS_DIRECTORY_PATH": configuration.server.environment_variables.LOGS_DIRECTORY_PATH,
            "ERROR_LOG_GROUP_NAME": log_groups["ERROR"].log_group_name,
            "ACCESS_LOG_GROUP_NAME": log_groups["ACCESS"].log_group_name,
            "APPLICATION_LOG_GROUP_NAME": log_groups["APPLICATION"].log_group_name,
        },
        logging=ecs.LogDriver.aws_logs(stream_prefix="LoggingLogs"),
    )

    logging_container.add_mount_points(
        ecs.MountPoint(
            source_volume="ServerVolume",
            container_path=configuration.server.storage.container_mount_point,
            read_only=True,
        )
    )

    ecs.Ec2Service(
        stack,
        "LoggingService",
        cluster=cluster,
        daemon=True,
        task_definition=logging_task,
    )
