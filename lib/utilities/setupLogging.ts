import * as cdk from "@aws-cdk/core";
import * as ecs from "@aws-cdk/aws-ecs";
import * as logs from "@aws-cdk/aws-logs";

import * as path from "path";

import { Environment } from "../environment";

export default function setupLogging(
  stack: cdk.Stack,
  environment: Environment,
  task: ecs.TaskDefinition
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

  let loggingContainer = task.addContainer("LoggingContainer", {
    image: ecs.ContainerImage.fromAsset(
      path.join(__dirname, "../../src/server/utilities/logging")
    ),
    memoryLimitMiB: 256,
    environment: {
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
}
