import tldextract

import aws_cdk as cdk
import aws_cdk.aws_autoscaling as autoscaling
import aws_cdk.aws_autoscaling_hooktargets as autoscaling_hooktargets
import aws_cdk.aws_backup as backup
import aws_cdk.aws_cloudwatch as cloudwatch
import aws_cdk.aws_cloudwatch_actions as cw_actions
import aws_cdk.aws_devopsguru as devopsguru
import aws_cdk.aws_lambda as λ
import aws_cdk.aws_sns as sns
import aws_cdk.aws_sns_subscriptions as subscriptions

from constructs import Construct

from .configuration import Configuration
from .computation_stack import ComputationStack
from .domain_stack import DomainStack
from .email_stack import EmailStack
from .persistent_storage_stack import PersistentStorageStack
from .server_stack import ServerStack


class OperationStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        configuration: Configuration,
        domain_stack: DomainStack,
        computation_stack: ComputationStack,
        email_stack: EmailStack,
        persistent_storage_stack: PersistentStorageStack,
        server_stack: ServerStack,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Backup

        backup_plan = backup.BackupPlan.daily_monthly1_year_retention(
            self, f"{self.stack_name}-BackupPlan", persistent_storage_stack.backup_vault
        )

        backup_plan.add_selection(
            "EmailSuppressionListBackup",
            resources=[
                backup.BackupResource.from_dynamo_db_table(
                    persistent_storage_stack.email_suppression_list
                )
            ],
        )

        backup_plan.add_selection(
            "ServerBlockStorageBackup",
            resources=[
                backup.BackupResource.from_arn(
                    f"arn:{self.partition}:ec2:{self.region}:{self.account}:volume/{server_stack.container_instance.volume_id}"
                )
            ],
        )

        # Alarms

        system_operations_topic = sns.Topic(self, "SystemOperationsTopic")

        subdomain, domain, suffix = tldextract.extract(configuration.domain_name)

        system_operations_topic.add_subscription(
            subscriptions.EmailSubscription(f"admins@{domain}.{suffix}")
        )

        all_concurrent_executions_metric = λ.Function.metric_all_concurrent_executions(
            period=cdk.Duration.minutes(5), statistic="max"
        )

        all_concurrent_executions_alarm = all_concurrent_executions_metric.create_alarm(
            self,
            "AllConcurrentExecutionsAlarm",
            evaluation_periods=1,
            threshold=100,
            treat_missing_data=cloudwatch.TreatMissingData.IGNORE,
        )

        all_concurrent_executions_alarm.add_alarm_action(
            cw_actions.SnsAction(system_operations_topic)
        )

        autoscaling.LifecycleHook(
            self,
            "InstanceTerminationLifecycleHook",
            auto_scaling_group=server_stack.service.cluster.autoscaling_group,
            lifecycle_transition=autoscaling.LifecycleTransition.INSTANCE_TERMINATING,
            notification_target=autoscaling_hooktargets.TopicHook(
                system_operations_topic
            ),
        )

        # Automatic monitoring

        devopsguru.CfnNotificationChannel(
            self,
            "OperationsNotificationChannel",
            config=devopsguru.CfnNotificationChannel.NotificationChannelConfigProperty(
                sns=devopsguru.CfnNotificationChannel.SnsChannelConfigProperty(
                    topic_arn=system_operations_topic.topic_arn
                )
            ),
        )

        devopsguru.CfnResourceCollection(
            self,
            "ResourceCollection",
            resource_collection_filter=devopsguru.CfnResourceCollection.ResourceCollectionFilterProperty(
                cloud_formation=devopsguru.CfnResourceCollection.CloudFormationCollectionFilterProperty(
                    stack_names=[
                        domain_stack.stack_name,
                        persistent_storage_stack.stack_name,
                        email_stack.stack_name,
                        computation_stack.stack_name,
                        server_stack.stack_name,
                    ]
                )
            ),
        )
