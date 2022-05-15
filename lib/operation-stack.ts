import * as autoscaling from "aws-cdk-lib/aws-autoscaling";
import * as autoscaling_hooktargets from "aws-cdk-lib/aws-autoscaling-hooktargets";
import * as backup from "aws-cdk-lib/aws-backup";
import * as cdk from "aws-cdk-lib";
import * as cw_actions from "aws-cdk-lib/aws-cloudwatch-actions";
import * as devopsguru from "aws-cdk-lib/aws-devopsguru";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as sns from "aws-cdk-lib/aws-sns";
import * as subscriptions from "aws-cdk-lib/aws-sns-subscriptions";

import { Construct } from "constructs";
import { Environment } from "./environment";

import { ComputationStack } from "./computation-stack";
import { DomainStack } from "./domain-stack";
import { EmailStack } from "./email-stack";
import { PersistentStorageStack } from "./persistent-storage-stack";
import { ServerStack } from "./server-stack";

type OperationStackProps = cdk.StackProps & {
  environment: Environment;
  domainStack: DomainStack;
  computationStack: ComputationStack;
  emailStack: EmailStack;
  persistentStorageStack: PersistentStorageStack;
  serverStack: ServerStack;
};

export class OperationStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: OperationStackProps) {
    super(scope, id, props);

    const environment = props.environment;

    // Backup

    let backupPlan = backup.BackupPlan.dailyWeeklyMonthly5YearRetention(
      this,
      `${this.stackName}-BackupPlan`,
      props.persistentStorageStack.backupVault
    );

    backupPlan.addSelection("EmailSuppressionListBackup", {
      resources: [
        backup.BackupResource.fromDynamoDbTable(
          props.persistentStorageStack.emailSuppressionList
        ),
      ],
    });

    backupPlan.addSelection("ServerBlockStorageBackup", {
      resources: [
        backup.BackupResource.fromArn(
          `arn:${this.partition}:ec2:${this.region}:${this.account}:volume/${props.serverStack.containerInstance.volumeId}`
        ),
      ],
    });

    // Alarms

    let systemOperationsTopic = new sns.Topic(this, "SystemOperationsTopic");

    systemOperationsTopic.addSubscription(
      new subscriptions.EmailSubscription(
        `admins@${props.domainStack.domainName}`
      )
    );

    let allConcurrentExecutionsMetric =
      lambda.Function.metricAllConcurrentExecutions({
        period: cdk.Duration.minutes(5),
        statistic: "max",
      });

    let allConcurrentExecutionsAlarm =
      allConcurrentExecutionsMetric.createAlarm(
        this,
        "AllConcurrentExecutionsAlarm",
        { evaluationPeriods: 1, threshold: 100 }
      );

    allConcurrentExecutionsAlarm.addAlarmAction(
      new cw_actions.SnsAction(systemOperationsTopic)
    );

    let serverAutoScalingGroup =
      props.serverStack.service.cluster.autoscalingGroup;

    if (!serverAutoScalingGroup)
      throw Error("Server autoscaling group is not defined");

    new autoscaling.LifecycleHook(this, "InstanceTerminationLifecycleHook", {
      autoScalingGroup: serverAutoScalingGroup,
      lifecycleTransition: autoscaling.LifecycleTransition.INSTANCE_TERMINATING,
      notificationTarget: new autoscaling_hooktargets.TopicHook(
        systemOperationsTopic
      ),
    });

    // Automatic monitoring

    new devopsguru.CfnNotificationChannel(
      this,
      "OperationsNotificationChannel",
      { config: { sns: { topicArn: systemOperationsTopic.topicArn } } }
    );

    let stacks: cdk.Stack[] = [
      props.domainStack,
      props.computationStack,
      props.emailStack,
      props.persistentStorageStack,
      props.serverStack,
    ];

    new devopsguru.CfnResourceCollection(this, "ResourceCollection", {
      resourceCollectionFilter: {
        cloudFormation: { stackNames: stacks.map((stack) => stack.stackName) },
      },
    });
  }
}
