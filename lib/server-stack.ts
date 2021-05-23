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

import * as environment from "./.env.json";

import mountEbsVolume from "./utilities/mountEbsVolume";
import getContainerInstanceId from "./utilities/getContainerInstanceId";
import setEc2UserPassword from "./utilities/setEc2UserPassword";

const VERIFIED_EMAIL_RECIPIENTS = ["nitebelt@gmail.com"];

type ServerStackProps = cdk.StackProps & {
  computationStateMachine: sfn.StateMachine;
  emailSuppressionListArn: string;
  notificationApi: apigateway.CfnApi;
  domainName: string;
  hostedZone: route53.IHostedZone;
  serverCertificate: acm.Certificate;
  emailConfigurationSetName: string;
  serverSecretKeyName: string;
  spreadsheetBucketArn: string;
};

export class ServerStack extends cdk.Stack {
  constructor(scope: cdk.Construct, id: string, props: ServerStackProps) {
    super(scope, id, props);

    const {
      computationStateMachine,
      emailSuppressionListArn,
      notificationApi,
      spreadsheetBucketArn,
      domainName,
      hostedZone,
      serverCertificate,
      emailConfigurationSetName,
    } = props;

    let serverSecretKey = new secretsmanager.Secret(this, "ServerSecretKey");
    let serverUserPassword = new secretsmanager.Secret(
      this,
      "ServerUserPassword"
    );

    let spreadsheetBucket = s3.Bucket.fromBucketArn(
      this,
      "SpreadsheetBucket",
      spreadsheetBucketArn
    );

    let emailSuppressionList = dynamodb.Table.fromTableArn(
      this,
      "EmailSuppressionList",
      emailSuppressionListArn
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
    emailSuppressionList.grantReadData(serverRole);
    serverSecretKey.grantRead(serverRole);

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
        EMAIL_CONFIGURATION_SET_NAME: emailConfigurationSetName,
        EMAIL_SUPPRESSION_LIST_NAME: emailSuppressionList.tableName,
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

    let serverVpc = new ec2.Vpc(this, "ServerVpc", {
      subnetConfiguration: [
        { name: "ServerSubnet", subnetType: ec2.SubnetType.PUBLIC },
      ],
    });

    let serverCluster = new ecs.Cluster(this, "ServerCluster", {
      vpc: serverVpc,
      capacity: {
        maxCapacity: 1,
        instanceType: ec2.InstanceType.of(
          ec2.InstanceClass.T3,
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
      },
      containerInsights: true,
    });

    mountEbsVolume(
      serverEbsVolume.deviceName,
      serverEbsVolume.mountPoint,
      serverCluster
    );

    setEc2UserPassword(serverCluster, serverUserPassword);

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
        openListener: environment.production ? true : false,
      }
    );

    let serverInstanceId = getContainerInstanceId(this, serverCluster);
    serverService.service.addPlacementConstraints(
      ecs.PlacementConstraint.memberOf(`ec2InstanceId == '${serverInstanceId}'`)
    );

    if (!environment.production) {
      let serverSecurityGroup = new ec2.SecurityGroup(
        this,
        "ServerSecurityGroup",
        { vpc: serverVpc }
      );

      environment.allowedCidrBlocks.map((cidrBlock) =>
        serverSecurityGroup.addIngressRule(
          ec2.Peer.ipv4(cidrBlock),
          ec2.Port.allTcp()
        )
      );

      serverService.loadBalancer.addSecurityGroup(serverSecurityGroup);
    }

    let outputs = {
      SpreadsheetBucketName: spreadsheetBucket.bucketName,
      ComputationStateMachineArn: computationStateMachine.stateMachineArn,
      NotificationApiEndpoint: `${notificationApi.attrApiEndpoint}/default`,
      EmailSuppressionListName: emailSuppressionList.tableName,
      ServerSecretKeyArn: serverSecretKey.secretArn,
    };

    for (let [outputName, outputValue] of Object.entries(outputs)) {
      new cdk.CfnOutput(this, outputName, { value: outputValue });
    }
  }
}
