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
        spreadsheet_bucket: s3.Bucket,
        application_docker_file: Optional[str] = None,
        additional_permissions: Optional[list[iam.PolicyStatement]] = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        server_secret_key = secretsmanager.Secret(self, "ServerSecretKey")

        # Server permissions

        server_role = iam.Role(
            self,
            "ServerRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )

        spreadsheet_bucket.grant_read_write(server_role)
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
                )
            ],
        )

        test_users = [] if configuration.production else configuration.server.test_users

        environment_variables = {
            "ENV": "PROD",
            "TEST_USERS": json.dumps(test_users, default=OmegaConf.to_container),
            "AWS_DEFAULT_REGION": self.region,
            "SPREADSHEET_BUCKET_NAME": spreadsheet_bucket.bucket_name,
            "COMPUTATION_STATE_MACHINE_ARN": computation_state_machine.state_machine_arn,
            "NOTIFICATION_API_ENDPOINT": f"wss://{notification_api.ref}.execute-api.{self.region}.amazonaws.com/default",
            "EMAIL_SENDER": f"no-reply@{configuration.domain_name}",
            "EMAIL_CONFIGURATION_SET_NAME": email_configuration_set_name,
            "EMAIL_SUPPRESSION_LIST_NAME": email_suppression_list.table_name,
        } | dict(configuration.server.environment_variables)

        server_container = server_task.add_container(
            "ServerContainer",
            image=ecs.ContainerImage.from_asset(
                "nitecap/server", file=application_docker_file
            ),
            memory_limit_mib=3328,
            environment=environment_variables,
            secrets={"SECRET_KEY": ecs.Secret.from_secrets_manager(server_secret_key)},
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

        # Server hardware

        server_vpc = ec2.Vpc(
            self,
            "ServerVpc",
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="ServerSubnet", subnet_type=ec2.SubnetType.PUBLIC
                )
            ],
        )

        ebs_delete_on_termination = (
            False if configuration.production or configuration.transition else True
        )

        server_cluster = ecs.Cluster(
            self,
            "ServerCluster",
            vpc=server_vpc,
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
                            delete_on_termination=ebs_delete_on_termination,
                        ),
                    )
                ],
            ),
        )

        # SSH connection

        server_cluster.connections.allow_from(
            ec2.Peer.ipv4(service_ip_range("EC2_INSTANCE_CONNECT", self.region)),
            ec2.Port.tcp(22),
        )

        server_cluster.autoscaling_group.add_user_data(
            "yum install -y ec2-instance-connect"
        )

        mount_ebs_volume(
            server_cluster,
            configuration.server.storage.device_name,
            configuration.server.storage.device_mount_point,
        )

        setup_logging(self, server_cluster, configuration)

        self.container_instance = describe_container_instance(self, server_cluster)

        server_task.add_placement_constraint(
            ecs.PlacementConstraint.member_of(
                f"ec2InstanceId == '{self.container_instance.instance_id}'"
            )
        )

        server_certificate = acm.DnsValidatedCertificate(
            self,
            "Certificate",
            hosted_zone=hosted_zone,
            domain_name=configuration.domain_name,
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

        if not configuration.production:
            server_security_group = ec2.SecurityGroup(
                self, "ServerSecurityGroup", vpc=server_vpc
            )

            for cidr_block in configuration.allowed_cidr_blocks:
                server_security_group.add_ingress_rule(
                    ec2.Peer.ipv4(cidr_block), ec2.Port.all_tcp()
                )

            self.service.load_balancer.add_security_group(server_security_group)

        for variable_name, variable_value in environment_variables.items():
            cdk.CfnOutput(self, variable_name, value=variable_value)

        cdk.CfnOutput(
            self, "EnvironmentVariables", value=" ".join(environment_variables.keys())
        )
