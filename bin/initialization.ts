#!/usr/bin/env node
import * as cdk from "@aws-cdk/core";
import { ComputationStack } from "../lib/computation-stack";
import { DomainStack } from "../lib/domain-stack";
import { EmailStack } from "../lib/email-stack";
import { OperationsStack } from "../lib/operations-stack";
import { PersistentStorageStack } from "../lib/persistent-storage-stack";
import { ServerStack } from "../lib/server-stack";
import { TransitionStack } from "../lib/utilities/transition/transition-stack";
import { TransitionParameterStack } from "../lib/utilities/transition/parameter-stack";

import environment from "./.env";

let app = new cdk.App();
let stage = new cdk.Stage(app, "NitecapDevelopment", {
  env: {
    region: environment.region,
    account: environment.account,
  },
});

let domainStack = new DomainStack(stage, "DomainStack", { environment });

let persistentStorageStack = new PersistentStorageStack(
  stage,
  "PersistentStorageStack",
  {
    environment,
    subdomainName: domainStack.subdomainName,
  }
);

let emailStack = new EmailStack(stage, "EmailStack", {
  domainName: domainStack.domainName,
  subdomainName: domainStack.subdomainName,
  hostedZone: domainStack.hostedZone,
  emailSuppressionList: persistentStorageStack.emailSuppressionList,
});

let computationStack = new ComputationStack(stage, "ComputationStack", {
  environment,
  spreadsheetBucket: persistentStorageStack.spreadsheetBucket,
});

let serverStackProps = {
  environment,
  computationStateMachine: computationStack.computationStateMachine,
  emailSuppressionList: persistentStorageStack.emailSuppressionList,
  snapshotIdParameter: persistentStorageStack.snapshotIdParameter,
  notificationApi: computationStack.notificationApi,
  domainName: domainStack.domainName,
  subdomainName: domainStack.subdomainName,
  hostedZone: domainStack.hostedZone,
  emailConfigurationSetName: emailStack.configurationSetName,
  serverCertificate: domainStack.certificate,
  spreadsheetBucket: persistentStorageStack.spreadsheetBucket,
};

new TransitionStack(stage, "TransitionStack", {
  serverStackProps,
  parameters: new TransitionParameterStack(stage, "TransitionParameterStack"),
});

// let serverStack = new ServerStack(stage, "ServerStack", serverStackProps);

// let stacks = {
//   computationStack,
//   domainStack,
//   emailStack,
//   persistentStorageStack,
//   serverStack,
// };

// new OperationsStack(stage, "OperationsStack", { environment, ...stacks });
