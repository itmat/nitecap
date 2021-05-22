#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "@aws-cdk/core";
import { ComputationStack } from "../lib/computation-stack";
import { DomainStack } from "../lib/domain-stack";
import { EmailStack as EmailComplianceStack } from "../lib/compliance/email-stack";
import { PersistentStorageStack } from "../lib/persistent-storage-stack";
import { ServerStack } from "../lib/server-stack";

const app = new cdk.App();

const environment = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION,
};

let domainStack = new DomainStack(app, "NitecapDomainStack-dev", {
  env: environment,
});

let emailComplianceStack = new EmailComplianceStack(
  app,
  "NitecapEmailComplianceStack-dev",
  {
    env: environment,
  }
);

let persistentStorageStack = new PersistentStorageStack(
  app,
  "NitecapPersistentStorageStack-dev",
  {
    env: environment,
    domainName: domainStack.domainName,
  }
);

let computationStack = new ComputationStack(
  app,
  "NitecapComputationStack-dev",
  {
    env: environment,
    spreadsheetBucketArn: persistentStorageStack.spreadsheetBucket.bucketArn,
  }
);

let serverStack = new ServerStack(app, "NitecapServerStack-dev", {
  env: environment,
  computationStateMachine: computationStack.computationStateMachine,
  emailSuppressionList: emailComplianceStack.emailSuppressionList,
  notificationApi: computationStack.notificationApi,
  domainName: domainStack.domainName,
  hostedZone: domainStack.hostedZone,
  serverSecretKeyName: "NitebeltServerSecretKey",
  serverCertificate: domainStack.certificate,
  spreadsheetBucketArn: persistentStorageStack.spreadsheetBucket.bucketArn,
});
