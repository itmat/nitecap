#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "@aws-cdk/core";
import { NitecapStack } from "../lib/nitecap-stack";
import { EmailStack as EmailComplianceStack } from "../lib/compliance/email-stack";

const app = new cdk.App();

const environment = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION,
};

let emailComplianceStack = new EmailComplianceStack(
  app,
  "EmailComplianceStack-dev",
  {
    env: environment,
  }
);

new NitecapStack(app, "NitecapStack-dev", {
  emailSuppressionList: emailComplianceStack.emailSuppressionList,
  env: environment,
});
