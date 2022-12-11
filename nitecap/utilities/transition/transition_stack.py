import aws_cdk as cdk
import aws_cdk.custom_resources as cr
import aws_cdk.aws_iam as iam
import aws_cdk.aws_lambda as λ
import aws_cdk.aws_ssm as ssm

from copy import copy, deepcopy
from constructs import Construct

from ...configuration import Configuration
from ...server_stack import ServerStack

from .parameter_stack import TransitionParameterStack


class TransitionStack(ServerStack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        parameters: TransitionParameterStack,
        **kwargs,
    ) -> None:
        arguments = copy(kwargs)

        # Transition server

        arguments["application_docker_file"] = "utilities/transition/Dockerfile"
        arguments["snapshot_id_parameter"] = parameters.previous_snapshot_id_parameter
        arguments["additional_permissions"] = [
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ssm:GetParameter"],
                resources=[parameters.snapshot_lambda_name_parameter.parameter_arn],
            ),
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["lambda:InvokeFunction"],
                resources=["*"],
            ),
        ]

        configuration: Configuration = deepcopy(kwargs["configuration"])

        configuration.domain_name = f"transition.{configuration.domain_name}"
        configuration.server.environment_variables.SNAPSHOT_LAMBDA_NAME_PARAMETER = (
            "\\" + parameters.snapshot_lambda_name_parameter.parameter_name
        )

        arguments["configuration"] = configuration

        super().__init__(scope, construct_id, **arguments)

        # Snapshot taking lambda

        transition_wait_condition_handle = cdk.CfnWaitConditionHandle(
            self, "TransitionWaitConditionHandle"
        )

        snapshot_lambda = λ.Function(
            self,
            "SnapshotLambda",
            code=λ.Code.from_asset("nitecap/utilities/transition"),
            handler="take_snapshot.handler",
            runtime=λ.Runtime.PYTHON_3_9,
            timeout=cdk.Duration.minutes(15),
            environment={
                "SNAPSHOT_ID_PARAMETER_NAME": kwargs[
                    "snapshot_id_parameter"
                ].parameter_name,
                "TRANSITION_SERVER_INSTANCE_ID": self.container_instance.instance_id,
                "TRANSITION_SERVER_BLOCK_STORAGE_ID": self.container_instance.volume_id,
                "WAIT_CONDITION_HANDLE_URL": transition_wait_condition_handle.ref,
            },
        )

        query_policy = iam.PolicyStatement()
        query_policy.add_actions("ec2:DescribeInstances", "ec2:DescribeSnapshots")
        query_policy.add_resources("*")

        terminate_instance_policy = iam.PolicyStatement()
        terminate_instance_policy.add_actions("ec2:TerminateInstances")
        terminate_instance_policy.add_resources(
            f"arn:{self.partition}:ec2:{self.region}:{self.account}:instance/{self.container_instance.instance_id}"
        )

        create_snapshot_policy = iam.PolicyStatement()
        create_snapshot_policy.add_actions("ec2:CreateSnapshot")
        create_snapshot_policy.add_resources(
            f"arn:{self.partition}:ec2:{self.region}::snapshot/*",
            f"arn:{self.partition}:ec2:{self.region}:{self.account}:volume/{self.container_instance.volume_id}",
        )

        for policy in (query_policy, terminate_instance_policy, create_snapshot_policy):
            snapshot_lambda.add_to_role_policy(policy)

        kwargs["snapshot_id_parameter"].grant_write(snapshot_lambda)

        put_snapshot_lambda_name_parameter = cr.AwsCustomResource(
            self,
            "PutSnapshotLambdaNameParameter",
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                resources=[parameters.snapshot_lambda_name_parameter.parameter_arn],
            ),
            on_update=cr.AwsSdkCall(
                service="SSM",
                action="putParameter",
                parameters={
                    "Name": parameters.snapshot_lambda_name_parameter.parameter_name,
                    "Value": snapshot_lambda.function_name,
                    "Overwrite": True,
                },
                physical_resource_id=cr.PhysicalResourceId.of(
                    snapshot_lambda.function_arn
                ),
            ),
        )

        transition_wait_condition = cdk.CfnWaitCondition(
            self,
            "TransitionWaitCondition",
            count=1,
            handle=transition_wait_condition_handle.ref,
            timeout="43200",
        )

        transition_wait_condition.node.add_dependency(
            put_snapshot_lambda_name_parameter
        )
