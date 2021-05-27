import * as cdk from "@aws-cdk/core";
import * as secretsmanager from "@aws-cdk/aws-secretsmanager";
import * as ssm from "@aws-cdk/aws-ssm";

export class ParameterStack extends cdk.Stack {
  readonly serverSecretKey: secretsmanager.Secret;
  readonly serverUserPassword: secretsmanager.Secret;
  readonly serverBlockStorageSnapshotId: ssm.StringParameter;
  readonly snapshotLambdaName: ssm.StringParameter;

  constructor(scope: cdk.Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    this.serverSecretKey = new secretsmanager.Secret(this, "ServerSecretKey");
    this.serverUserPassword = new secretsmanager.Secret(
      this,
      "ServerUserPassword"
    );

    this.serverBlockStorageSnapshotId = new ssm.StringParameter(
      this,
      "SnapshotIdParameter",
      { stringValue: "TBD" }
    );

    this.snapshotLambdaName = new ssm.StringParameter(
      this,
      "SnapshotLambdaParameter",
      { stringValue: "TBD" }
    );
  }
}
