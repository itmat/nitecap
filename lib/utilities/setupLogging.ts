import * as cdk from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as logs from "aws-cdk-lib/aws-logs";

import * as path from "path";

import { Environment } from "../environment";

export default function setupLogging(
  stack: cdk.Stack,
  cluster: ecs.Cluster,
  environment: Environment
) {
  let configuration = {
    retention: logs.RetentionDays.INFINITE,
    removalPolicy: environment.production
      ? cdk.RemovalPolicy.RETAIN
      : cdk.RemovalPolicy.DESTROY,
  };

  let logGroups = {
    error: new logs.LogGroup(stack, "ServerErrorLogGroup", configuration),
    access: new logs.LogGroup(stack, "ServerAccessLogGroup", configuration),
    application: new logs.LogGroup(
      stack,
      "ServerApplicationLogGroup",
      configuration
    ),
  };

  let loggingTaks = new ecs.Ec2TaskDefinition(stack, "LoggingTask", {
    taskRole: new iam.Role(stack, "LoggingRole", {
      assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          "CloudWatchAgentServerPolicy"
        ),
      ],
    }),
    volumes: [
      {
        name: "ServerVolume",
        host: { sourcePath: environment.server.storage.deviceMountPoint },
      },
    ],
  });

  let loggingContainer = loggingTaks.addContainer("LoggingContainer", {
    image: ecs.ContainerImage.fromAsset(
      path.join(__dirname, "../../src/server/utilities/logging")
    ),
    memoryLimitMiB: 256,
    environment: {
      LOGS_DIRECTORY_PATH: environment.server.variables.LOGS_DIRECTORY_PATH,
      ERROR_LOG_GROUP_NAME: logGroups.error.logGroupName,
      ACCESS_LOG_GROUP_NAME: logGroups.access.logGroupName,
      APPLICATION_LOG_GROUP_NAME: logGroups.application.logGroupName,
    },
    logging: ecs.LogDriver.awsLogs({ streamPrefix: "LoggingLogs" }),
  });

  loggingContainer.addMountPoints({
    sourceVolume: "ServerVolume",
    containerPath: environment.server.storage.containerMountPoint,
    readOnly: true,
  });

  new ecs.Ec2Service(stack, "LoggingService", {
    cluster,
    daemon: true,
    taskDefinition: loggingTaks,
  });
}
