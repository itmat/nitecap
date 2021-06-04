import * as autoscaling from "@aws-cdk/aws-autoscaling";
import * as autoscaling_hooktargets from "@aws-cdk/aws-autoscaling-hooktargets";
import * as backup from "@aws-cdk/aws-backup";
import * as cdk from "@aws-cdk/core";
import * as cw_actions from "@aws-cdk/aws-cloudwatch-actions";
import * as devopsguru from "@aws-cdk/aws-devopsguru";
import * as lambda from "@aws-cdk/aws-lambda";
import * as sns from "@aws-cdk/aws-sns";
import * as subscriptions from "@aws-cdk/aws-sns-subscriptions";

import { Environment } from "./environment";

import { ComputationStack } from "./computation-stack";
import { DomainStack } from "./domain-stack";
import { EmailStack } from "./email-stack";
import { PersistentStorageStack } from "./persistent-storage-stack";
import { ServerStack } from "./server-stack";

type OperationsStackProps = cdk.StackProps & {
  environment: Environment;
  domainStack: DomainStack;
  computationStack: ComputationStack;
  emailStack: EmailStack;
  persistentStorageStack: PersistentStorageStack;
  serverStack: ServerStack;
};

export class OperationsStack extends cdk.Stack {
  constructor(scope: cdk.Construct, id: string, props: OperationsStackProps) {
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

    // Outputs

    let outputs = {
      ComputationStateMachineArn:
        props.computationStack.computationStateMachine.stateMachineArn,
      EmailConfigurationSetName: props.emailStack.configurationSetName,
      EmailSuppressionListName:
        props.persistentStorageStack.emailSuppressionList.tableName,
      NotificationApiEndpoint: `${props.computationStack.notificationApi.attrApiEndpoint}/default`,
      ServerSecretKeyArn: props.serverStack.serverSecretKey.secretArn,
      SpreadsheetBucketName:
        props.persistentStorageStack.spreadsheetBucket.bucketName,
    };

    for (let [outputName, outputValue] of Object.entries(outputs)) {
      new cdk.CfnOutput(this, outputName, { value: outputValue });
    }
  }
}
