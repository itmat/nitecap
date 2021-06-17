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
import * as ssm from "@aws-cdk/aws-ssm";

import { UlimitName } from "@aws-cdk/aws-ecs/lib/container-definition";

import * as path from "path";

import mountEbsVolume from "./utilities/mountEbsVolume";
import describeContainerInstance from "./utilities/describeContainerInstance";
import setEc2UserPassword from "./utilities/setEc2UserPassword";
import setupLogging from "./utilities/setupLogging";

import { Environment } from "./environment";

export type ServerStackProps = cdk.StackProps & {
  environment: Environment;
  computationStateMachine: sfn.StateMachine;
  emailSuppressionList: dynamodb.Table;
  notificationApi: apigateway.CfnApi;
  domainName: string;
  subdomainName: string;
  hostedZone: route53.IHostedZone;
  snapshotIdParameter: ssm.StringParameter;
  emailConfigurationSetName: string;
  spreadsheetBucket: s3.Bucket;
  applicationDockerfile?: string;
  additionalPermissions?: iam.PolicyStatement[];
};

export type ContainerInstance = { instanceId: string; volumeId: string };

export class ServerStack extends cdk.Stack {
  readonly containerInstance: ContainerInstance;
  readonly serverSecretKey: secretsmanager.Secret;
  readonly service: ecs_patterns.ApplicationLoadBalancedEc2Service;

  constructor(scope: cdk.Construct, id: string, props: ServerStackProps) {
    super(scope, id, props);

    const environment = props.environment;

    // Server secrets

    this.serverSecretKey = new secretsmanager.Secret(this, "ServerSecretKey");
    let serverUserPassword = new secretsmanager.Secret(
      this,
      "ServerUserPassword"
    );

    // Server permissions

    let serverRole = new iam.Role(this, "ServerRole", {
      assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
    });

    props.spreadsheetBucket.grantReadWrite(serverRole);
    props.computationStateMachine.grantRead(serverRole);
    props.computationStateMachine.grantStartExecution(serverRole);
    props.emailSuppressionList.grantReadData(serverRole);
    this.serverSecretKey.grantRead(serverRole);

    serverRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["ses:SendEmail"],
        resources: [
          `arn:${this.partition}:ses:${this.region}:${this.account}:identity/${props.domainName}`,
          `arn:${this.partition}:ses:${this.region}:${this.account}:identity/${props.subdomainName}`,
        ],
      })
    );

    if (props.additionalPermissions)
      for (let statement of props.additionalPermissions)
        serverRole.addToPolicy(statement);

    // Server software

    let serverTask = new ecs.Ec2TaskDefinition(this, "ServerTask", {
      taskRole: serverRole,
      volumes: [
        {
          name: "ServerVolume",
          host: { sourcePath: environment.server.storage.deviceMountPoint },
        },
      ],
    });

    let serverContainer = serverTask.addContainer("ServerContainer", {
      image: ecs.ContainerImage.fromAsset(
        path.join(__dirname, "../src/server"),
        { file: props.applicationDockerfile }
      ),
      memoryLimitMiB: 1536,
      environment: {
        ...environment.server.variables,
        AWS_DEFAULT_REGION: this.region,
        SERVER_SECRET_KEY_ARN: this.serverSecretKey.secretArn,
        SPREADSHEET_BUCKET_NAME: props.spreadsheetBucket.bucketName,
        COMPUTATION_STATE_MACHINE_ARN:
          props.computationStateMachine.stateMachineArn,
        NOTIFICATION_API_ENDPOINT: `wss://${props.notificationApi.ref}.execute-api.${this.region}.amazonaws.com/default`,
        EMAIL_SENDER: `no-reply@${props.subdomainName}`,
        EMAIL_CONFIGURATION_SET_NAME: props.emailConfigurationSetName,
        EMAIL_SUPPRESSION_LIST_NAME: props.emailSuppressionList.tableName,
      },
      portMappings: [
        {
          containerPort: 5000,
          protocol: ecs.Protocol.TCP,
        },
      ],
      logging: ecs.LogDriver.awsLogs({ streamPrefix: "ServerTaskLogs" }),
    });

    serverContainer.addMountPoints({
      sourceVolume: "ServerVolume",
      containerPath: environment.server.storage.containerMountPoint,
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
            deviceName: environment.server.storage.deviceName,
            volume: autoscaling.BlockDeviceVolume.ebsFromSnapshot(
              props.snapshotIdParameter.stringValue,
              {
                deleteOnTermination: environment.production ? false : true,
              }
            ),
          },
        ],
      },
      containerInsights: true,
    });

    mountEbsVolume(
      environment.server.storage.deviceName,
      environment.server.storage.deviceMountPoint,
      serverCluster
    );

    setupLogging(this, serverCluster, environment);
    setEc2UserPassword(serverCluster, serverUserPassword);

    this.containerInstance = describeContainerInstance(this, serverCluster);

    serverTask.addPlacementConstraint(
      ecs.PlacementConstraint.memberOf(
        `ec2InstanceId == '${this.containerInstance.instanceId}'`
      )
    );

    let serverCertificate = new acm.DnsValidatedCertificate(this, "Certificate", {
      hostedZone: props.hostedZone,
      domainName: props.subdomainName,
    });

    this.service = new ecs_patterns.ApplicationLoadBalancedEc2Service(
      this,
      "ServerService",
      {
        taskDefinition: serverTask,
        desiredCount: 1,
        cluster: serverCluster,
        domainName: props.subdomainName,
        domainZone: props.hostedZone,
        certificate: serverCertificate,
        redirectHTTP: true,
        openListener: environment.production ? true : false,
      }
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

      this.service.loadBalancer.addSecurityGroup(serverSecurityGroup);
    }
  }
}
