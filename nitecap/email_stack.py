import tldextract

import aws_cdk as cdk
import aws_cdk.custom_resources as cr
import aws_cdk.aws_dynamodb as dynamodb
import aws_cdk.aws_lambda as λ
import aws_cdk.aws_iam as iam
import aws_cdk.aws_route53 as route53
import aws_cdk.aws_ses as ses
import aws_cdk.aws_sns as sns
import aws_cdk.aws_sns_subscriptions as subscriptions

from constructs import Construct
from .configuration import Configuration


class EmailStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        configuration: Configuration,
        email_suppression_list: dynamodb.Table,
        hosted_zone: route53.IHostedZone,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        subdomain, domain, suffix = tldextract.extract(configuration.domain_name)

        # Compliance

        bounces_topic = sns.Topic(self, "BouncesTopic")
        complaints_topic = sns.Topic(self, "ComplaintsTopics")

        bounces_lambda = λ.Function(
            self,
            "BouncesLambda",
            code=λ.Code.from_asset("nitecap/compliance"),
            handler="bounces.handler",
            runtime=λ.Runtime.PYTHON_3_9,
            environment={
                "SOFT_BOUNCES_RECIPIENT": f"admin@{domain}.{suffix}",
                "EMAIL_SUPPRESSION_LIST_NAME": email_suppression_list.table_name,
            },
        )

        email_suppression_list.grant_write_data(bounces_lambda)

        bounces_lambda.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ses:SendEmail"],
                resources=[
                    f"arn:{self.partition}:ses:{self.region}:{self.account}:identity/admins@{domain}.{suffix}"
                ],
            )
        )

        bounces_topic.add_subscription(subscriptions.LambdaSubscription(bounces_lambda))
        complaints_topic.add_subscription(
            subscriptions.EmailSubscription(f"admins@{domain}.{suffix}")
        )

        # Configuration

        configuration_set = ses.CfnConfigurationSet(
            self,
            "ConfigurationSet",
            name=f"ConfigurationSet-{configuration.domain_name.replace('.', '_')}",
        )

        self.configuration_set_name = configuration_set.name

        compliance_configuration = {
            "Bounce": bounces_topic,
            "Complaint": complaints_topic,
        }

        for event_type, destination in compliance_configuration.items():
            cr.AwsCustomResource(
                self,
                f"Email{event_type}Destination",
                policy=cr.AwsCustomResourcePolicy.from_statements(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["ses:CreateConfigurationSetEventDestination"],
                            resources=[
                                f"arn:{self.partition}:ses:{self.region}:{self.account}:configuration-set/{self.configuration_set_name}"
                            ],
                        )
                    ]
                ),
                on_update=cr.AwsSdkCall(
                    service="SESV2",
                    action="createConfigurationSetEventDestination",
                    parameters={
                        "ConfigurationSetName": self.configuration_set_name,
                        "EventDestinationName": f"Topic-{destination.node.addr}",
                        "EventDestination": {
                            "Enabled": True,
                            "MatchingEventTypes": [event_type.upper()],
                            "SnsDestination": {
                                "TopicArn": destination.topic_arn,
                            },
                        },
                    },
                    physical_resource_id=cr.PhysicalResourceId.of(
                        destination.topic_arn
                    ),
                ),
            )

        email_identity = cr.AwsCustomResource(
            self,
            "EmailIdentity",
            policy=cr.AwsCustomResourcePolicy.from_statements(
                statements=[
                    iam.PolicyStatement(
                        effect=iam.Effect.ALLOW,
                        actions=["ses:CreateEmailIdentity", "ses:DeleteEmailIdentity"],
                        resources=[
                            f"arn:{self.partition}:ses:{self.region}:{self.account}:identity/{configuration.domain_name}"
                        ],
                    )
                ]
            ),
            on_update=cr.AwsSdkCall(
                service="SESV2",
                action="createEmailIdentity",
                parameters={
                    "EmailIdentity": configuration.domain_name,
                    "ConfigurationSetName": self.configuration_set_name,
                },
                physical_resource_id=cr.PhysicalResourceId.of(
                    configuration.domain_name
                ),
            ),
            on_delete=cr.AwsSdkCall(
                service="SESV2",
                action="deleteEmailIdentity",
                parameters={"EmailIdentity": configuration.domain_name},
            ),
        )

        # DKIM tokens

        for token_index in range(3):
            token = email_identity.get_response_field(
                f"DkimAttributes.Tokens.{token_index}"
            )

            route53.CnameRecord(
                self,
                f"DomainKeysIdentifiedMailRecord-{token_index}",
                zone=hosted_zone,
                record_name=f"{token}._domainkey.{configuration.domain_name}",
                domain_name=f"{token}.dkim.amazonses.com",
            )
