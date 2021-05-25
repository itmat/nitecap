#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "@aws-cdk/core";
import { ComputationStack } from "../lib/computation-stack";
import { DomainStack } from "../lib/domain-stack";
import { EmailStack } from "../lib/email-stack";
import { PersistentStorageStack } from "../lib/persistent-storage-stack";
import { ServerStack } from "../lib/server-stack";

const app = new cdk.App();

let domainStack = new DomainStack(app, "NitecapDomainStack-dev", {});

let persistentStorageStack = new PersistentStorageStack(
  app,
  "NitecapPersistentStorageStack-dev",
  { domainName: domainStack.domainName }
);

let emailStack = new EmailStack(app, "NitecapEmailStack-dev", {
  domainName: domainStack.domainName,
  hostedZone: domainStack.hostedZone,
  emailSuppressionListArn: persistentStorageStack.emailSuppressionList.tableArn,
});

let computationStack = new ComputationStack(
  app,
  "NitecapComputationStack-dev",
  { spreadsheetBucket: persistentStorageStack.spreadsheetBucket }
);

let serverStack = new ServerStack(app, "NitecapServerStack-dev", {
  computationStateMachine: computationStack.computationStateMachine,
  emailSuppressionList: persistentStorageStack.emailSuppressionList,
  serverBlockDevice: persistentStorageStack.serverBlockDevice,
  notificationApi: computationStack.notificationApi,
  domainName: domainStack.domainName,
  hostedZone: domainStack.hostedZone,
  emailConfigurationSetName: emailStack.configurationSetName,
  serverSecretKeyName: "NitebeltServerSecretKey",
  serverCertificate: domainStack.certificate,
  spreadsheetBucket: persistentStorageStack.spreadsheetBucket,
});
