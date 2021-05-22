import * as apigateway from "@aws-cdk/aws-apigatewayv2";
import * as autoscaling from "@aws-cdk/aws-autoscaling";
import * as acm from "@aws-cdk/aws-certificatemanager";
import * as cdk from "@aws-cdk/core";
import * as dynamodb from "@aws-cdk/aws-dynamodb";
import * as ec2 from "@aws-cdk/aws-ec2";
import * as ecs from "@aws-cdk/aws-ecs";
import * as ecs_patterns from "@aws-cdk/aws-ecs-patterns";
import * as iam from "@aws-cdk/aws-iam";
import * as route53 from "@aws-cdk/aws-route53";
import * as s3 from "@aws-cdk/aws-s3";
import * as secretsmanager from "@aws-cdk/aws-secretsmanager";
import * as sfn from "@aws-cdk/aws-stepfunctions";

import { UlimitName } from "@aws-cdk/aws-ecs/lib/container-definition";

import * as path from "path";

import mountEbsVolume from "./utilities/mountEbsVolume";
import getContainerInstanceId from "./utilities/getContainerInstanceId";

const VERIFIED_EMAIL_RECIPIENTS = ["nitebelt@gmail.com"];

type ServerStackProps = cdk.StackProps & {
  computationStateMachine: sfn.StateMachine;
  emailSuppressionList: dynamodb.Table;
  notificationApi: apigateway.CfnApi;
  domainName: string;
  hostedZone: route53.IHostedZone;
  serverCertificate: acm.Certificate;
  serverSecretKeyName: string;
  spreadsheetBucketArn: string;
};

export class ServerStack extends cdk.Stack {
  constructor(scope: cdk.Construct, id: string, props: ServerStackProps) {
    super(scope, id, props);

    const {
      computationStateMachine,
      notificationApi,
      spreadsheetBucketArn,
      domainName,
      hostedZone,
      serverCertificate
    } = props;

    let spreadsheetBucket = s3.Bucket.fromBucketArn(
      this,
      "SpreadsheetBucket",
      spreadsheetBucketArn
    );

    // Server persistent storage

    const serverEbsVolume = {
      deviceName: "/dev/xvdb",
      mountPoint: "/mnt/storage",
      snapshotId: "snap-011e8fd69817cf783",
    };

    // Server permissions

    let serverRole = new iam.Role(this, "ServerRole", {
      assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
    });

    spreadsheetBucket.grantReadWrite(serverRole);
    computationStateMachine.grantRead(serverRole);
    computationStateMachine.grantStartExecution(serverRole);
    props.emailSuppressionList.grantReadData(serverRole);

    serverRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["ses:SendEmail"],
        resources: [
          `arn:${this.partition}:ses:${this.region}:${this.account}:identity/${domainName}`,
          ...VERIFIED_EMAIL_RECIPIENTS.map(
            (recipient) =>
              `arn:${this.partition}:ses:${this.region}:${this.account}:identity/${recipient}`
          ),
        ],
      })
    );

    let serverSecretKey = secretsmanager.Secret.fromSecretNameV2(
      this,
      "ServerSecretKey",
      props.serverSecretKeyName
    );

    serverSecretKey.grantRead(serverRole);

    // Server software

    let serverTask = new ecs.Ec2TaskDefinition(this, "ServerTask", {
      taskRole: serverRole,
      volumes: [
        {
          name: "ServerVolume",
          host: {
            sourcePath: serverEbsVolume.mountPoint,
          },
        },
      ],
    });

    let serverContainer = serverTask.addContainer("ServerContainer", {
      image: ecs.ContainerImage.fromAsset(
        path.join(__dirname, "../src/server")
      ),
      memoryLimitMiB: 1536,
      environment: {
        ENVIRONMENT: "PROD",
        LOG_FILE: "/nitecap_web/log",
        AWS_DEFAULT_REGION: this.region,
        SERVER_SECRET_KEY_ARN: serverSecretKey.secretArn,
        SPREADSHEET_BUCKET_NAME: spreadsheetBucket.bucketName,
        COMPUTATION_STATE_MACHINE_ARN: computationStateMachine.stateMachineArn,
        NOTIFICATION_API_ENDPOINT: `wss://${notificationApi.ref}.execute-api.${this.region}.amazonaws.com/default`,
        EMAIL_SENDER: `no-reply@${domainName}`,
        EMAIL_SUPPRESSION_LIST_NAME: props.emailSuppressionList.tableName,
      },
      portMappings: [
        {
          containerPort: 5000,
          protocol: ecs.Protocol.TCP,
        },
      ],
      logging: ecs.LogDriver.awsLogs({ streamPrefix: "ServerLogs" }),
    });

    serverContainer.addMountPoints({
      sourceVolume: "ServerVolume",
      containerPath: "/nitecap_web",
      readOnly: false,
    });

    serverContainer.addUlimits({
      softLimit: 1048576,
      hardLimit: 1048576,
      name: UlimitName.NOFILE,
    });

    // Server hardware

    let serverVpc = ec2.Vpc.fromLookup(this, "ServerVpc", { isDefault: true });

    let serverCluster = new ecs.Cluster(this, "ServerCluster", {
      vpc: serverVpc,
      capacity: {
        maxCapacity: 1,
        instanceType: ec2.InstanceType.of(
          ec2.InstanceClass.T2,
          ec2.InstanceSize.MEDIUM
        ),
        blockDevices: [
          {
            deviceName: serverEbsVolume.deviceName,
            volume: autoscaling.BlockDeviceVolume.ebsFromSnapshot(
              serverEbsVolume.snapshotId,
              {
                deleteOnTermination: true,
              }
            ),
          },
        ],
        keyName: "NitecapServerKey",
      },
      containerInsights: true,
    });

    mountEbsVolume(
      serverEbsVolume.deviceName,
      serverEbsVolume.mountPoint,
      serverCluster
    );

    let serverService = new ecs_patterns.ApplicationLoadBalancedEc2Service(
      this,
      "ServerService",
      {
        cluster: serverCluster,
        memoryLimitMiB: 1792,
        desiredCount: 1,
        taskDefinition: serverTask,
        domainName,
        domainZone: hostedZone,
        certificate: serverCertificate,
        redirectHTTP: true,
      }
    );

    let serverInstanceId = getContainerInstanceId(this, serverCluster);
    serverService.service.addPlacementConstraints(
      ecs.PlacementConstraint.memberOf(`ec2InstanceId == '${serverInstanceId}'`)
    );

    let outputs = {
      ComputationStateMachineArn: computationStateMachine.stateMachineArn,
      EmailSuppressionListName: props.emailSuppressionList.tableName,
      NotificationApiEndpoint: `${notificationApi.attrApiEndpoint}/default`,
      ServerSecretKeyArn: serverSecretKey.secretArn,
      SpreadsheetBucketName: spreadsheetBucket.bucketName,
    };

    for (let [outputName, outputValue] of Object.entries(outputs)) {
      new cdk.CfnOutput(this, outputName, { value: outputValue });
    }
  }
}
