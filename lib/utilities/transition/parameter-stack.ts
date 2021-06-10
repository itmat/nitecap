import * as cdk from "@aws-cdk/core";
import * as ssm from "@aws-cdk/aws-ssm";

import previousPersistentStorageStack from "./.env";

export class TransitionParameterStack extends cdk.Stack {
  readonly snapshotLambdaNameParameter: ssm.StringParameter;
  readonly previousSnapshotIdParameter: ssm.StringParameter;

  constructor(scope: cdk.Construct, id: string, props?: cdk.StackProps) {
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