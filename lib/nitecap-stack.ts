import * as apigateway from "@aws-cdk/aws-apigatewayv2";
import * as cdk from "@aws-cdk/core";
import * as dynamodb from "@aws-cdk/aws-dynamodb";
import * as iam from "@aws-cdk/aws-iam";
import * as s3 from "@aws-cdk/aws-s3";

import { CfnAccount as ApiGatewayCfnAccount } from "@aws-cdk/aws-apigateway";

export class NitecapStack extends cdk.Stack {
  constructor(scope: cdk.Construct, id: string, props?: cdk.StackProps) {
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

    new ApiGatewayCfnAccount(this, "NotificationApiAccount", {
      cloudWatchRoleArn: notificationApiRole.roleArn,
    });

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
  }
}
