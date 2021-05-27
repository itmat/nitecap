#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "@aws-cdk/core";
import { BackupStack } from "../lib/backup-stack";
import { ComputationStack } from "../lib/computation-stack";
import { DomainStack } from "../lib/domain-stack";
import { EmailStack } from "../lib/email-stack";
import { PersistentStorageStack } from "../lib/persistent-storage-stack";
import { ServerStack } from "../lib/server-stack";
import { ParameterStack } from "../lib/parameter-stack";
import { TransitionStack } from "../lib/utilities/transition/transition-stack";

import { Environment } from "../lib/environment";
import * as env from "./.env.json";

const environment: Environment = env;

const app = new cdk.App();

let parameterStack = new ParameterStack(app, "NitecapParameterStack-dev");

let domainStack = new DomainStack(app, "NitecapDomainStack-dev", {
  environment,
});

let backupStack = new BackupStack(app, "NitecapBackupStack-dev", {
  environment,
});

let persistentStorageStack = new PersistentStorageStack(
  app,
  "NitecapPersistentStorageStack-dev",
  {
    environment,
    domainName: domainStack.domainName,
    backupPlan: backupStack.backupPlan,
  }
);

let emailStack = new EmailStack(app, "NitecapEmailStack-dev", {
  environment,
  domainName: domainStack.domainName,
  hostedZone: domainStack.hostedZone,
  emailSuppressionListArn: persistentStorageStack.emailSuppressionList.tableArn,
});

let computationStack = new ComputationStack(
  app,
  "NitecapComputationStack-dev",
  { environment, spreadsheetBucket: persistentStorageStack.spreadsheetBucket }
);

let serverStackProps = {
  environment,
  computationStateMachine: computationStack.computationStateMachine,
  emailSuppressionList: persistentStorageStack.emailSuppressionList,
  serverBlockDevice: persistentStorageStack.serverBlockDevice,
  notificationApi: computationStack.notificationApi,
  domainName: domainStack.domainName,
  hostedZone: domainStack.hostedZone,
  backupPlan: backupStack.backupPlan,
  emailConfigurationSetName: emailStack.configurationSetName,
  serverSecretKey: parameterStack.serverSecretKey,
  serverUserPassword: parameterStack.serverUserPassword,
  serverCertificate: domainStack.certificate,
  spreadsheetBucket: persistentStorageStack.spreadsheetBucket,
};

let transitionStack = new TransitionStack(app, "NitecapTransitionStack-dev", {
  serverStackProps,
  snapshotLambdaName: parameterStack.snapshotLambdaName,
  snapshotIdParameter: parameterStack.serverBlockStorageSnapshotId,
});

// let serverStack = new ServerStack(
//   app,
//   "NitecapServerStack-dev",
//   serverStackProps
// );

// serverStack.addDependency(transitionStack);
