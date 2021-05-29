import * as autoscaling from "@aws-cdk/aws-autoscaling";
import * as autoscaling_hooktargets from "@aws-cdk/aws-autoscaling-hooktargets";
import * as backup from "@aws-cdk/aws-backup";
import * as cdk from "@aws-cdk/core";
import * as cw_actions from "@aws-cdk/aws-cloudwatch-actions";
import * as lambda from "@aws-cdk/aws-lambda";
import * as sns from "@aws-cdk/aws-sns";
import * as subscriptions from "@aws-cdk/aws-sns-subscriptions";

import { Environment } from "./environment";

import { ComputationStack } from "./computation-stack";
import { EmailStack } from "./email-stack";
import { ParameterStack } from "./parameter-stack";
import { PersistentStorageStack } from "./persistent-storage-stack";
import { ServerStack } from "./server-stack";

type OperationsStackProps = cdk.StackProps & {
  environment: Environment;
  computationStack: ComputationStack;
  emailStack: EmailStack;
  parameterStack: ParameterStack;
  persistentStorageStack: PersistentStorageStack;
  serverStack: ServerStack;
};

export class OperationsStack extends cdk.Stack {
  constructor(scope: cdk.Construct, id: string, props: OperationsStackProps) {
    super(scope, id, props);

    const environment = props.environment;

    // Backup

    let backupVault = new backup.BackupVault(this, "BackupVault", {
      removalPolicy: environment.production
        ? cdk.RemovalPolicy.RETAIN
        : cdk.RemovalPolicy.DESTROY,
    });

    let backupPlan = backup.BackupPlan.dailyWeeklyMonthly5YearRetention(
      this,
      `${this.stackName}-BackupPlan`,
      backupVault
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

    let computationBackendAlarmsTopic = new sns.Topic(
      this,
      "ComputationBackendAlarmsTopic"
    );

    environment.email.computationBackendAlarmsRecipients.map((recipient) =>
      computationBackendAlarmsTopic.addSubscription(
        new subscriptions.EmailSubscription(recipient)
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
      new cw_actions.SnsAction(computationBackendAlarmsTopic)
    );

    let serverAlarmsTopic = new sns.Topic(this, "ServerAlarmsTopic");
    environment.email.serverAlarmsRecipients.map((recipient) =>
      serverAlarmsTopic.addSubscription(
        new subscriptions.EmailSubscription(recipient)
      )
    );

    let serverAutoScalingGroup = props.serverStack.service.cluster.autoscalingGroup;

    if (!serverAutoScalingGroup)
      throw Error("Server autoscaling group is not defined")

    new autoscaling.LifecycleHook(this, "InstanceTerminationLifecycleHook", {
      autoScalingGroup: serverAutoScalingGroup,
      lifecycleTransition: autoscaling.LifecycleTransition.INSTANCE_TERMINATING,
      notificationTarget: new autoscaling_hooktargets.TopicHook(
        serverAlarmsTopic
      )
    });

    // Outputs

    let outputs = {
      ComputationStateMachineArn:
        props.computationStack.computationStateMachine.stateMachineArn,
      EmailConfigurationSetName: props.emailStack.configurationSetName,
      EmailSuppressionListName:
        props.persistentStorageStack.emailSuppressionList.tableName,
      NotificationApiEndpoint: `${props.computationStack.notificationApi.attrApiEndpoint}/default`,
      ServerSecretKeyArn: props.parameterStack.serverSecretKey.secretArn,
      SpreadsheetBucketName:
        props.persistentStorageStack.spreadsheetBucket.bucketName,
    };

    for (let [outputName, outputValue] of Object.entries(outputs)) {
      new cdk.CfnOutput(this, outputName, { value: outputValue });
    }
  }
}
