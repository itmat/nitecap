import * as apigateway from "@aws-cdk/aws-apigatewayv2";
import * as autoscaling from "@aws-cdk/aws-autoscaling";
import * as cdk from "@aws-cdk/core";
import * as dynamodb from "@aws-cdk/aws-dynamodb";
import * as ec2 from "@aws-cdk/aws-ec2";
import * as ecs from "@aws-cdk/aws-ecs";
import * as ecs_patterns from "@aws-cdk/aws-ecs-patterns";
import * as elb from "@aws-cdk/aws-elasticloadbalancingv2";
import * as iam from "@aws-cdk/aws-iam";
import * as lambda from "@aws-cdk/aws-lambda";
import * as s3 from "@aws-cdk/aws-s3";
import * as secretsmanager from "@aws-cdk/aws-secretsmanager";
import * as sfn from "@aws-cdk/aws-stepfunctions";
import * as tasks from "@aws-cdk/aws-stepfunctions-tasks";

import { CfnAccount as ApiGatewayCfnAccount } from "@aws-cdk/aws-apigateway";
import { UlimitName } from "@aws-cdk/aws-ecs/lib/container-definition";

import * as path from "path";

import mountEbsVolume from "./mountEbsVolume";
import getContainerInstanceId from "./getContainerInstanceId";

const DOMAIN_NAME = "nitebelt.org";
const VERIFIED_EMAIL_RECIPIENTS = ["nitebelt@gmail.com"];

function toPascalCase(name: string) {
  return name
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join("");
}

export class NitecapStack extends cdk.Stack {
  constructor(
    scope: cdk.Construct,
    id: string,
    props: cdk.StackProps & {
      emailSuppressionList: dynamodb.Table;
      serverSecretKeyName: string;
    }
  ) {
    super(scope, id, props);

    let spreadsheetBucket = new s3.Bucket(this, "SpreadsheetBucket", {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      lifecycleRules: [
        {
          transitions: [
            {
              transitionAfter: cdk.Duration.days(90),
              storageClass: s3.StorageClass.INFREQUENT_ACCESS,
            },
          ],
        },
      ],
      autoDeleteObjects: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // Table of connections

    let connectionTable = new dynamodb.Table(this, "ConnectionTable", {
      partitionKey: {
        name: "connectionId",
        type: dynamodb.AttributeType.STRING,
      },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    const userId = "userId";
    connectionTable.addGlobalSecondaryIndex({
      indexName: `${userId}-index`,
      partitionKey: { name: userId, type: dynamodb.AttributeType.STRING },
      projectionType: dynamodb.ProjectionType.KEYS_ONLY,
    });

    // Notification API

    let notificationApi = new apigateway.CfnApi(this, "NotificationApi", {
      name: "NotificationApi",
      protocolType: "WEBSOCKET",
      routeSelectionExpression: "$request.body.action",
    });

    let notificationApiRole = new iam.Role(this, "NotificationApiRole", {
      assumedBy: new iam.ServicePrincipal("apigateway.amazonaws.com"),
      managedPolicies: [
        {
          managedPolicyArn:
            "arn:aws:iam::aws:policy/service-role/AmazonAPIGatewayPushToCloudWatchLogs",
        },
      ],
    });

    let notificationApiAccount = new ApiGatewayCfnAccount(
      this,
      "NotificationApiAccount",
      {
        cloudWatchRoleArn: notificationApiRole.roleArn,
      }
    );

    notificationApiRole.attachInlinePolicy(
      new iam.Policy(this, "NotificationApiPolicy", {
        statements: [
          new iam.PolicyStatement({
            effect: iam.Effect.ALLOW,
            actions: ["dynamodb:UpdateItem", "dynamodb:DeleteItem"],
            resources: [connectionTable.tableArn],
          }),
        ],
      })
    );

    let disconnectIntegration = new apigateway.CfnIntegration(
      this,
      "DisconnectIntegration",
      {
        apiId: notificationApi.ref,
        integrationType: "AWS",
        integrationMethod: "POST",
        integrationUri: `arn:aws:apigateway:${this.region}:dynamodb:action/DeleteItem`,
        templateSelectionExpression: "\\$default",
        credentialsArn: notificationApiRole.roleArn,
        requestTemplates: {
          "\\$default": JSON.stringify({
            TableName: connectionTable.tableName,
            Key: {
              connectionId: { S: "$context.connectionId" },
            },
          }),
        },
      }
    );

    let notificationApiDisconnectRoute = new apigateway.CfnRoute(
      this,
      "DisconnectRoute",
      {
        apiId: notificationApi.ref,
        routeKey: "$disconnect",
        target: `integrations/${disconnectIntegration.ref}`,
      }
    );

    let defaultIntegration = new apigateway.CfnIntegration(
      this,
      "DefaultIntegration",
      {
        apiId: notificationApi.ref,
        integrationType: "AWS",
        integrationMethod: "POST",
        integrationUri: `arn:aws:apigateway:${this.region}:dynamodb:action/UpdateItem`,
        templateSelectionExpression: "\\$default",
        credentialsArn: notificationApiRole.roleArn,
        requestTemplates: {
          "\\$default": JSON.stringify({
            TableName: connectionTable.tableName,
            Key: { connectionId: { S: "$context.connectionId" } },
            UpdateExpression: `SET ${userId} = :value`,
            ExpressionAttributeValues: { ":value": { S: "$input.body" } },
          }),
        },
      }
    );

    let notificationApiDefaultRoute = new apigateway.CfnRoute(
      this,
      "DefaultRoute",
      {
        apiId: notificationApi.ref,
        routeKey: "$default",
        target: `integrations/${defaultIntegration.ref}`,
      }
    );

    let notificationApiStage = new apigateway.CfnStage(
      this,
      "NotificationApiStage",
      {
        apiId: notificationApi.ref,
        stageName: "default",
        defaultRouteSettings: {
          dataTraceEnabled: true,
          loggingLevel: "ERROR",
          detailedMetricsEnabled: false,
        },
      }
    );

    notificationApiStage.addDependsOn(notificationApiAccount);

    let notificationApiDeployment = new apigateway.CfnDeployment(
      this,
      "NotificationApiDeployment",
      {
        apiId: notificationApi.ref,
        stageName: notificationApiStage.stageName,
      }
    );

    notificationApiDeployment.addDependsOn(notificationApiDisconnectRoute);
    notificationApiDeployment.addDependsOn(notificationApiDefaultRoute);

    // Computation engine

    let ALGORITHMS = ["cosinor", "ls", "arser", "jtk", "one_way_anova"];

    let computationLambdas = new Map<string, lambda.DockerImageFunction>();
    for (let algorithm of ALGORITHMS) {
      computationLambdas.set(
        algorithm,
        new lambda.DockerImageFunction(
          this,
          `${toPascalCase(algorithm)}ComputationLambda`,
          {
            memorySize: 10240,
            timeout: cdk.Duration.minutes(15),
            code: lambda.DockerImageCode.fromImageAsset(
              path.join(__dirname, "../src/computation"),
              {
                file: `algorithms/${algorithm}/Dockerfile`,
              }
            ),
            tracing: lambda.Tracing.ACTIVE,
            environment: {
              CONNECTION_TABLE_NAME: connectionTable.tableName,
              NOTIFICATION_API_ENDPOINT: `https://${notificationApi.ref}.execute-api.${this.region}.amazonaws.com/default`,
              SPREADSHEET_BUCKET_NAME: spreadsheetBucket.bucketName,
            },
          }
        )
      );
    }

    for (let computationLambda of computationLambdas.values()) {
      spreadsheetBucket.grantRead(computationLambda);
      spreadsheetBucket.grantPut(computationLambda);
      connectionTable.grantReadData(computationLambda);

      computationLambda.addToRolePolicy(
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: ["execute-api:Invoke", "execute-api:ManageConnections"],
          resources: [
            `arn:aws:execute-api:${this.region}:${this.account}:${notificationApi.ref}/*`,
          ],
        })
      );
    }

    let computationTasks = new Map<string, tasks.LambdaInvoke>();
    for (let [algorithm, computationLambda] of computationLambdas.entries()) {
      computationTasks.set(
        algorithm,
        new tasks.LambdaInvoke(
          this,
          `${toPascalCase(algorithm)}ComputationTask`,
          { lambdaFunction: computationLambda }
        )
      );
    }

    let algorithmChoice = new sfn.Choice(this, "AlgorithmChoice");
    for (let [
      algorithm,
      algorithmComputationTask,
    ] of computationTasks.entries()) {
      algorithmChoice.when(
        sfn.Condition.stringEquals("$.algorithm", algorithm),
        algorithmComputationTask
      );
    }

    let computationStateMachine = new sfn.StateMachine(
      this,
      "ComputationStateMachine",
      {
        definition: algorithmChoice,
        timeout: cdk.Duration.hours(2),
        tracingEnabled: true,
      }
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
          `arn:${this.partition}:ses:${this.region}:${this.account}:identity/${DOMAIN_NAME}`,
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
        EMAIL_SENDER: `no-reply@${DOMAIN_NAME}`,
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

    let serverLoadBalancer = new elb.ApplicationLoadBalancer(
      this,
      "ServerLoadBalancer",
      { loadBalancerName: "nitebelt", vpc: serverVpc, internetFacing: true }
    );

    spreadsheetBucket.addCorsRule({
      allowedMethods: [s3.HttpMethods.GET],
      allowedOrigins: [
        `http://${serverLoadBalancer.loadBalancerDnsName}`,
        "http://localhost:5000",
      ],
    });

    let serverService = new ecs_patterns.ApplicationLoadBalancedEc2Service(
      this,
      "ServerService",
      {
        cluster: serverCluster,
        memoryLimitMiB: 1792,
        desiredCount: 1,
        taskDefinition: serverTask,
        loadBalancer: serverLoadBalancer,
      }
    );

    let serverInstanceId = getContainerInstanceId(this, serverCluster);
    serverService.service.addPlacementConstraints(
      ecs.PlacementConstraint.memberOf(`ec2InstanceId == '${serverInstanceId}'`)
    );

    let outputs = {
      SpreadsheetBucketName: spreadsheetBucket.bucketName,
      NotificationApiEndpoint: `${notificationApi.attrApiEndpoint}/default`,
      ComputationStateMachineArn: computationStateMachine.stateMachineArn,
      EmailSuppressionListName: props.emailSuppressionList.tableName,
    };

    for (let [outputName, outputValue] of Object.entries(outputs)) {
      new cdk.CfnOutput(this, outputName, { value: outputValue });
    }
  }
}
