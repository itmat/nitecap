import json

import aws_cdk as cdk
import aws_cdk.aws_apigatewayv2 as apigateway
import aws_cdk.aws_dynamodb as dynamodb
import aws_cdk.aws_iam as iam
import aws_cdk.aws_lambda as λ
import aws_cdk.aws_s3 as s3
import aws_cdk.aws_stepfunctions as sfn
import aws_cdk.aws_stepfunctions_tasks as tasks

from aws_cdk.aws_apigateway import CfnAccount as ApiGatewayCfnAccount

from constructs import Construct
from .utilities import to_pascal_case


class ComputationStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        spreadsheet_bucket: s3.Bucket,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Table of connections

        connection_table = dynamodb.Table(
            self,
            "ConnectionTable",
            partition_key={
                "name": "connectionId",
                "type": dynamodb.AttributeType.STRING,
            },
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        userId = "userId"
        connection_table.add_global_secondary_index(
            index_name=f"{userId}-index",
            partition_key={"name": userId, "type": dynamodb.AttributeType.STRING},
            projection_type=dynamodb.ProjectionType.KEYS_ONLY,
        )

        # Notification API

        self.notification_api = apigateway.CfnApi(
            self,
            "NotificationApi",
            name="NotificationApi",
            protocol_type="WEBSOCKET",
            route_selection_expression="$request.body.action",
        )

        notification_api_role = iam.Role(
            self,
            "NotificationApiRole",
            assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonAPIGatewayPushToCloudWatchLogs"
                )
            ],
        )

        notification_api_account = ApiGatewayCfnAccount(
            self,
            "NotificationApiAccount",
            cloud_watch_role_arn=notification_api_role.role_arn,
        )

        notification_api_role.attach_inline_policy(
            iam.Policy(
                self,
                "NotificationApiPolicy",
                statements=[
                    iam.PolicyStatement(
                        effect=iam.Effect.ALLOW,
                        actions=["dynamodb:UpdateItem", "dynamodb:DeleteItem"],
                        resources=[connection_table.table_arn],
                    )
                ],
            )
        )

        disconnect_integration = apigateway.CfnIntegration(
            self,
            "DisconnectIntegration",
            api_id=self.notification_api.ref,
            integration_type="AWS",
            integration_method="POST",
            integration_uri=f"arn:{self.partition}:apigateway:{self.region}:dynamodb:action/DeleteItem",
            template_selection_expression="\\$default",
            credentials_arn=notification_api_role.role_arn,
            request_templates={
                "\\$default": json.dumps(
                    {
                        "TableName": connection_table.table_name,
                        "Key": {"connectionId": {"S": "$context.connectionId"}},
                    }
                )
            },
        )

        notification_api_disconnect_route = apigateway.CfnRoute(
            self,
            "DisconnectRoute",
            api_id=self.notification_api.ref,
            route_key="$disconnect",
            target=f"integrations/{disconnect_integration.ref}",
        )

        default_integration = apigateway.CfnIntegration(
            self,
            "DefaultIntegration",
            api_id=self.notification_api.ref,
            integration_type="AWS",
            integration_method="POST",
            integration_uri=f"arn:{self.partition}:apigateway:{self.region}:dynamodb:action/UpdateItem",
            template_selection_expression="\\$default",
            credentials_arn=notification_api_role.role_arn,
            request_templates={
                "\\$default": json.dumps(
                    {
                        "TableName": connection_table.table_name,
                        "Key": {"connectionId": {"S": "$context.connectionId"}},
                        "UpdateExpression": f"SET {userId} = :value",
                        "ExpressionAttributeValues": {":value": {"S": "$input.body"}},
                    }
                )
            },
        )

        notification_api_default_route = apigateway.CfnRoute(
            self,
            "DefaultRoute",
            api_id=self.notification_api.ref,
            route_key="$default",
            target=f"integrations/{default_integration.ref}",
        )

        notification_api_stage = apigateway.CfnStage(
            self,
            "NotificationApiStage",
            api_id=self.notification_api.ref,
            stage_name="default",
            default_route_settings={
                "dataTraceEnabled": True,
                "loggingLevel": "ERROR",
                "detailedMetricsEnabled": False,
            },
        )

        notification_api_stage.add_dependency(notification_api_account)

        notification_api_deployment = apigateway.CfnDeployment(
            self,
            "NotificationApiDeployment",
            api_id=self.notification_api.ref,
            stage_name=notification_api_stage.stage_name,
        )

        notification_api_deployment.add_dependency(notification_api_default_route)
        notification_api_deployment.add_dependency(notification_api_disconnect_route)

        # Computation engine

        ALGORITHMS = [
            "cosinor",
            "differential_cosinor",
            "ls",
            "arser",
            "jtk",
            "one_way_anova",
            "two_way_anova",
            "rain",
            "upside",
        ]

        computation_lambdas = {
            algorithm: λ.DockerImageFunction(
                self,
                f"{to_pascal_case(algorithm)}ComputationLambda",
                memory_size=10240,
                timeout=cdk.Duration.minutes(15),
                code=λ.DockerImageCode.from_image_asset(
                    "nitecap/computation", file=f"algorithms/{algorithm}/Dockerfile"
                ),
                environment={
                    "CONNECTION_TABLE_NAME": connection_table.table_name,
                    "NOTIFICATION_API_ENDPOINT": f"https://{self.notification_api.ref}.execute-api.{self.region}.amazonaws.com/default",
                    "SPREADSHEET_BUCKET_NAME": spreadsheet_bucket.bucket_name,
                },
            )
            for algorithm in ALGORITHMS
        }

        for computation_lambda in computation_lambdas.values():
            spreadsheet_bucket.grant_read_write(computation_lambda)
            connection_table.grant_read_data(computation_lambda)

            computation_lambda.add_to_role_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["execute-api:Invoke", "execute-api:ManageConnections"],
                    resources=[
                        f"arn:{self.partition}:execute-api:{self.region}:{self.account}:{self.notification_api.ref}/*",
                    ],
                )
            )

        computation_tasks = {
            algorithm: tasks.LambdaInvoke(
                self,
                f"{to_pascal_case(algorithm)}ComputationTask",
                lambda_function=computation_lambda,
            )
            for algorithm, computation_lambda in computation_lambdas.items()
        }

        algorithm_choice = sfn.Choice(self, "AlgorithmChoice")

        for algorithm, computation_task in computation_tasks.items():
            algorithm_choice.when(
                sfn.Condition.string_equals("$.algorithm", algorithm), computation_task
            )

        self.computation_state_machine = sfn.StateMachine(
            self,
            "ComputationStateMachine",
            definition=algorithm_choice,
            timeout=cdk.Duration.hours(2),
        )
