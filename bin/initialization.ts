#!/usr/bin/env node
import * as cdk from "@aws-cdk/core";
import { BackupStack } from "../lib/backup-stack";
import { ComputationStack } from "../lib/computation-stack";
import { DomainStack } from "../lib/domain-stack";
import { EmailStack } from "../lib/email-stack";
import { ParameterStack } from "../lib/parameter-stack";
import { PersistentStorageStack } from "../lib/persistent-storage-stack";
import { ServerStack } from "../lib/server-stack";
import { TransitionStack } from "../lib/utilities/transition/transition-stack";

import environment from "./.env";

let app = new cdk.App();
let stage = new cdk.Stage(app, "NitecapDevelopment", {
  env: {
    region: environment.region,
    account: environment.account,
  },
});

let parameterStack = new ParameterStack(stage, "ParameterStack");
let domainStack = new DomainStack(stage, "DomainStack", { environment });
let backupStack = new BackupStack(stage, "BackupStack", { environment });

let persistentStorageStack = new PersistentStorageStack(
  stage,
  "PersistentStorageStack",
  {
    environment,
    subdomainName: domainStack.subdomainName,
    backupPlan: backupStack.backupPlan,
  }
);

let emailStack = new EmailStack(stage, "EmailStack", {
  environment,
  subdomainName: domainStack.subdomainName,
  hostedZone: domainStack.hostedZone,
  emailSuppressionListArn: persistentStorageStack.emailSuppressionList.tableArn,
});

let computationStack = new ComputationStack(stage, "ComputationStack", {
  environment,
  spreadsheetBucket: persistentStorageStack.spreadsheetBucket,
});

let serverStackProps = {
  environment,
  computationStateMachine: computationStack.computationStateMachine,
  emailSuppressionList: persistentStorageStack.emailSuppressionList,
  serverBlockDevice: persistentStorageStack.serverBlockDevice,
  notificationApi: computationStack.notificationApi,
  subdomainName: domainStack.subdomainName,
  hostedZone: domainStack.hostedZone,
  backupPlan: backupStack.backupPlan,
  emailConfigurationSetName: emailStack.configurationSetName,
  serverSecretKey: parameterStack.serverSecretKey,
  serverUserPassword: parameterStack.serverUserPassword,
  serverCertificate: domainStack.certificate,
  spreadsheetBucket: persistentStorageStack.spreadsheetBucket,
};

// let transitionStack = new TransitionStack(app, "TransitionStack", {
//   serverStackProps,
//   snapshotLambdaName: parameterStack.snapshotLambdaName,
//   snapshotIdParameter: parameterStack.serverBlockStorageSnapshotId,
// });

let serverStack = new ServerStack(stage, "ServerStack", serverStackProps);

// serverStack.addDependency(transitionStack);
