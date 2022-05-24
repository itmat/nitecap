import * as cdk from "aws-cdk-lib";
import * as ssm from "aws-cdk-lib/aws-ssm";

import { Construct } from "constructs";

import previousPersistentStorageStack from "./.env";

export class TransitionParameterStack extends cdk.Stack {
  readonly snapshotLambdaNameParameter: ssm.StringParameter;
  readonly previousSnapshotIdParameter: ssm.StringParameter;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    this.snapshotLambdaNameParameter = new ssm.StringParameter(
      this,
      "SnapshotLambdaNameParameter",
      { stringValue: "TBD" }
    );

    this.previousSnapshotIdParameter = new ssm.StringParameter(
      this,
      "PreviousSnapshotIdParameter",
      { stringValue: previousPersistentStorageStack.serverStorageSnapshotId }
    );
  }
}
