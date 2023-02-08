import json
import tldextract

import aws_cdk as cdk
import aws_cdk.aws_apigatewayv2 as apigateway
import aws_cdk.aws_autoscaling as autoscaling
import aws_cdk.aws_certificatemanager as acm
import aws_cdk.aws_dynamodb as dynamodb
import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_ecs as ecs
import aws_cdk.aws_ecs_patterns as ecs_patterns
import aws_cdk.aws_iam as iam
import aws_cdk.aws_rds as rds
import aws_cdk.aws_route53 as route53
import aws_cdk.aws_s3 as s3
import aws_cdk.aws_secretsmanager as secretsmanager
import aws_cdk.aws_stepfunctions as sfn
import aws_cdk.aws_ssm as ssm

from typing import Optional
from omegaconf import OmegaConf
from constructs import Construct
from .configuration import Configuration

from .utilities import (
    describe_container_instance,
    mount_ebs_volume,
    service_ip_range,
    setup_firewall,
    setup_logging,
)


class ServerStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        configuration: Configuration,
        computation_state_machine: sfn.StateMachine,
        email_suppression_list: dynamodb.Table,
        notification_api: apigateway.CfnApi,
        hosted_zone: route53.IHostedZone,
        snapshot_id_parameter: ssm.StringParameter,
        email_configuration_set_name: str,
        analytics_bucket: s3.Bucket,
        storage_bucket: s3.Bucket,
        application_docker_file: Optional[str] = None,
        additional_permissions: Optional[list[iam.PolicyStatement]] = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        server_secret_key = secretsmanager.Secret(self, "ServerSecretKey")

        vpc = ec2.Vpc(
            self,
            "Vpc",
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="ServerSubnet", subnet_type=ec2.SubnetType.PUBLIC
                )
            ],
        )

        # Server hardware

        delete_ebs_volume_on_server_instance_termination = (
            False if configuration.production or configuration.transition else True
        )

        server_cluster = ecs.Cluster(
            self,
            "ServerCluster",
            vpc=vpc,
            capacity=ecs.AddCapacityOptions(
                max_capacity=1,
                instance_type=ec2.InstanceType.of(
                    ec2.InstanceClass.C6A, ec2.InstanceSize.LARGE
                ),
                machine_image=ecs.EcsOptimizedImage.amazon_linux2(
                    ecs.AmiHardwareType.STANDARD, cached_in_context=True
                ),
                block_devices=[
                    autoscaling.BlockDevice(
                        device_name=configuration.server.storage.device_name,
                        volume=autoscaling.BlockDeviceVolume.ebs_from_snapshot(
                            snapshot_id_parameter.string_value,
                            delete_on_termination=delete_ebs_volume_on_server_instance_termination,
                        ),
                    )
                ],
            ),
        )

        mount_ebs_volume(
            server_cluster,
            configuration.server.storage.device_name,
            configuration.server.storage.device_mount_point,
        )

        self.container_instance = describe_container_instance(server_cluster)

        # SSH access

        server_cluster.connections.allow_from(
            ec2.Peer.ipv4(service_ip_range("EC2_INSTANCE_CONNECT", self.region)),
            ec2.Port.tcp(22),
        )

        server_cluster.autoscaling_group.add_user_data(
            "yum install -y ec2-instance-connect"
        )

        # Database

        database_instance = rds.DatabaseInstance(
            self,
            "DatabaseInstance",
            vpc=vpc,
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_14_5
            ),
            allocated_storage=30,
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3, ec2.InstanceSize.MICRO
            ),
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            database_name="nitecap",
            publicly_accessible=False if configuration.production else True,
            delete_automated_backups=False if configuration.production else True,
            removal_policy=(
                cdk.RemovalPolicy.SNAPSHOT
                if configuration.production
                else cdk.RemovalPolicy.DESTROY
            ),
        )

        database_instance.connections.allow_default_port_from(server_cluster)

        if not configuration.production:
            for cidr_block in configuration.allowed_cidr_blocks:
                database_instance.connections.allow_default_port_from(
                    ec2.Peer.ipv4(cidr_block)
                )

        # Server permissions

        server_role = iam.Role(
            self,
            "ServerRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )

        analytics_bucket.grant_read_write(server_role)
        storage_bucket.grant_read_write(server_role)
        computation_state_machine.grant_read(server_role)
        computation_state_machine.grant_start_execution(server_role)
        email_suppression_list.grant_read_data(server_role)

        subdomain, domain, suffix = tldextract.extract(configuration.domain_name)

        server_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ses:SendEmail"],
                resources=[
                    f"arn:{self.partition}:ses:{self.region}:{self.account}:identity/{domain}.{suffix}",
                    f"arn:{self.partition}:ses:{self.region}:{self.account}:identity/{configuration.domain_name}",
                ],
            )
        )

        if additional_permissions:
            for statement in additional_permissions:
                server_role.add_to_policy(statement)

        # Server software

        server_task = ecs.Ec2TaskDefinition(
            self,
            "ServerTask",
            task_role=server_role,
            volumes=[
                ecs.Volume(
                    name="ServerVolume",
                    host=ecs.Host(
                        source_path=configuration.server.storage.device_mount_point
                    ),
                ),
            ],
        )

        environment_variables = dict(configuration.server.environment_variables) | {
            "ENV": "PROD",
            "AWS_DEFAULT_REGION": self.region,
            "ANALYTICS_BUCKET_NAME": analytics_bucket.bucket_name,
            "COMPUTATION_STATE_MACHINE_ARN": computation_state_machine.state_machine_arn,
            "NOTIFICATION_API_ENDPOINT": f"wss://{notification_api.ref}.execute-api.{self.region}.amazonaws.com/default",
            "EMAIL_SENDER": f"no-reply@{configuration.domain_name}",
            "EMAIL_CONFIGURATION_SET_NAME": email_configuration_set_name,
            "EMAIL_SUPPRESSION_LIST_NAME": email_suppression_list.table_name,
            "STORAGE_LOCATION": f"s3://{storage_bucket.bucket_name}",
            "TEST_USERS": json.dumps(
                configuration.testing.users, default=OmegaConf.to_container
            ),
        }

        server_container = server_task.add_container(
            "ServerContainer",
            image=ecs.ContainerImage.from_asset(
                "nitecap/server", file=application_docker_file
            ),
            memory_limit_mib=3328,
            environment=environment_variables,
            secrets={
                "DATABASE_SECRET": ecs.Secret.from_secrets_manager(
                    database_instance.secret
                ),
                "SECRET_KEY": ecs.Secret.from_secrets_manager(server_secret_key),
            },
            logging=ecs.LogDriver.aws_logs(stream_prefix="ServerTaskLogs"),
            port_mappings=[
                ecs.PortMapping(container_port=5000, protocol=ecs.Protocol.TCP)
            ],
        )

        server_container.add_mount_points(
            ecs.MountPoint(
                source_volume="ServerVolume",
                container_path=configuration.server.storage.container_mount_point,
                read_only=False,
            )
        )

        server_container.add_ulimits(
            ecs.Ulimit(
                soft_limit=1048576, hard_limit=1048576, name=ecs.UlimitName.NOFILE
            )
        )

        server_task.add_placement_constraint(
            ecs.PlacementConstraint.member_of(
                f"ec2InstanceId == '{self.container_instance.instance_id}'"
            )
        )

        setup_logging(server_cluster, configuration)

        server_certificate = acm.Certificate(
            self,
            "Certificate",
            domain_name=configuration.domain_name,
            validation=acm.CertificateValidation.from_dns(
                hosted_zone=hosted_zone,
            ),
        )

        self.service = ecs_patterns.ApplicationLoadBalancedEc2Service(
            self,
            "ServerService",
            task_definition=server_task,
            desired_count=1,
            cluster=server_cluster,
            domain_name=configuration.domain_name,
            domain_zone=hosted_zone,
            certificate=server_certificate,
            redirect_http=True,
            open_listener=True if configuration.production else False,
            min_healthy_percent=0,
        )

        self.service.target_group.set_attribute(
            "deregistration_delay.timeout_seconds", "0"
        )

        setup_firewall(self.service.load_balancer)

        if not configuration.production:
            for cidr_block in configuration.allowed_cidr_blocks:
                self.service.load_balancer.connections.allow_from(
                    ec2.Peer.ipv4(cidr_block), ec2.Port.all_tcp()
                )

        for variable_name, variable_value in environment_variables.items():
            cdk.CfnOutput(self, variable_name, value=variable_value)

        cdk.CfnOutput(
            self, "DatabaseSecretArn", value=database_instance.secret.secret_arn
        )

        cdk.CfnOutput(
            self, "EnvironmentVariables", value=" ".join(environment_variables.keys())
        )
