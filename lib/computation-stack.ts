import * as apigateway from "@aws-cdk/aws-apigatewayv2";
import * as cdk from "@aws-cdk/core";
import * as cw_actions from "@aws-cdk/aws-cloudwatch-actions";
import * as dynamodb from "@aws-cdk/aws-dynamodb";
import * as iam from "@aws-cdk/aws-iam";
import * as lambda from "@aws-cdk/aws-lambda";
import * as s3 from "@aws-cdk/aws-s3";
import * as sfn from "@aws-cdk/aws-stepfunctions";
import * as sns from "@aws-cdk/aws-sns";
import * as subscriptions from "@aws-cdk/aws-sns-subscriptions";
import * as tasks from "@aws-cdk/aws-stepfunctions-tasks";

import { CfnAccount as ApiGatewayCfnAccount } from "@aws-cdk/aws-apigateway";

import * as path from "path";

function toPascalCase(name: string) {
  return name
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join("");
}

const COMPUTATION_BACKEND_ALARMS_EMAIL = "nitebelt@gmail.com";

type ComputationStackProps = cdk.StackProps & { spreadsheetBucketArn: string };

export class ComputationStack extends cdk.Stack {
  readonly computationStateMachine: sfn.StateMachine;
  readonly notificationApi: apigateway.CfnApi;

  constructor(scope: cdk.Construct, id: string, props: ComputationStackProps) {
    super(scope, id, props);

    let spreadsheetBucket = s3.Bucket.fromBucketArn(
      this,
      "SpreadsheetBucket",
      props.spreadsheetBucketArn
    );

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

    this.notificationApi = new apigateway.CfnApi(this, "NotificationApi", {
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
        apiId: this.notificationApi.ref,
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
        apiId: this.notificationApi.ref,
        routeKey: "$disconnect",
        target: `integrations/${disconnectIntegration.ref}`,
      }
    );

    let defaultIntegration = new apigateway.CfnIntegration(
      this,
      "DefaultIntegration",
      {
        apiId: this.notificationApi.ref,
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
        apiId: this.notificationApi.ref,
        routeKey: "$default",
        target: `integrations/${defaultIntegration.ref}`,
      }
    );

    let notificationApiStage = new apigateway.CfnStage(
      this,
      "NotificationApiStage",
      {
        apiId: this.notificationApi.ref,
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
        apiId: this.notificationApi.ref,
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
              NOTIFICATION_API_ENDPOINT: `https://${this.notificationApi.ref}.execute-api.${this.region}.amazonaws.com/default`,
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
            `arn:aws:execute-api:${this.region}:${this.account}:${this.notificationApi.ref}/*`,
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

    this.computationStateMachine = new sfn.StateMachine(
      this,
      "ComputationStateMachine",
      {
        definition: algorithmChoice,
        timeout: cdk.Duration.hours(2),
        tracingEnabled: true,
      }
    );

    // Alarms

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

    let computationBackendAlarmsTopic = new sns.Topic(
      this,
      "ComputationBackendAlarmsTopic"
    );

    computationBackendAlarmsTopic.addSubscription(
      new subscriptions.EmailSubscription(COMPUTATION_BACKEND_ALARMS_EMAIL)
    );

    allConcurrentExecutionsAlarm.addAlarmAction(
      new cw_actions.SnsAction(computationBackendAlarmsTopic)
    );
  }
}
