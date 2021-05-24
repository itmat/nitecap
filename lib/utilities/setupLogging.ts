import * as cdk from "@aws-cdk/core";
import * as ecs from "@aws-cdk/aws-ecs";
import * as logs from "@aws-cdk/aws-logs";

import * as path from "path";

export default function setupLogging(
  stack: cdk.Stack,
  task: ecs.TaskDefinition
) {
  let errorLogGroup = new logs.LogGroup(stack, "ServerErrorLogGroup", {
    retention: logs.RetentionDays.INFINITE,
  });

  let accessLogGroup = new logs.LogGroup(stack, "ServerAccessLogGroup", {
    retention: logs.RetentionDays.INFINITE,
  });

  let applicationLogGroup = new logs.LogGroup(
    stack,
    "ServerApplicationLogGroup",
    { retention: logs.RetentionDays.INFINITE }
  );

  let loggingContainer = task.addContainer("LoggingContainer", {
    image: ecs.ContainerImage.fromAsset(
      path.join(__dirname, "../../src/server/logging")
    ),
    memoryLimitMiB: 256,
    environment: {
      ERROR_LOG_GROUP_NAME: errorLogGroup.logGroupName,
      ACCESS_LOG_GROUP_NAME: accessLogGroup.logGroupName,
      APPLICATION_LOG_GROUP_NAME: applicationLogGroup.logGroupName,
    },
    logging: ecs.LogDriver.awsLogs({ streamPrefix: "LoggingLogs" }),
  });

  loggingContainer.addMountPoints({
    sourceVolume: "ServerVolume",
    containerPath: "/nitecap_web",
    readOnly: false,
  });
}
