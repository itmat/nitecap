import * as cdk from "@aws-cdk/core";
import * as dynamodb from "@aws-cdk/aws-dynamodb";
import * as s3 from "@aws-cdk/aws-s3";
import * as ssm from "@aws-cdk/aws-ssm";

import { Environment } from "./environment";

type PersistentStorageStackProps = cdk.StackProps & {
  environment: Environment;
  subdomainName: string;
};

export class PersistentStorageStack extends cdk.Stack {
  readonly spreadsheetBucket: s3.Bucket;
  readonly emailSuppressionList: dynamodb.Table;
  readonly snapshotIdParameter: ssm.StringParameter;

  constructor(
    scope: cdk.Construct,
    id: string,
    props: PersistentStorageStackProps
  ) {
    super(scope, id, props);

    const environment = props.environment;

    let allowedCorsOrigins = [`https://${props.subdomainName}`];
    if (!environment.production)
      allowedCorsOrigins.push("http://localhost:5000");

    this.spreadsheetBucket = new s3.Bucket(this, "SpreadsheetBucket", {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      lifecycleRules: [
        {
          transitions: [
            {
              transitionAfter: cdk.Duration.days(90),
              storageClass: s3.StorageClass.INFREQUENT_ACCESS,
            },
          ],
        },
      ],
      cors: [
        {
          allowedMethods: [s3.HttpMethods.GET],
          allowedOrigins: allowedCorsOrigins,
        },
      ],
      autoDeleteObjects: environment.production ? false : true,
      removalPolicy: environment.production
        ? cdk.RemovalPolicy.RETAIN
        : cdk.RemovalPolicy.DESTROY,
    });

    this.emailSuppressionList = new dynamodb.Table(
      this,
      "EmailSuppressionList",
      {
        partitionKey: {
          name: "email",
          type: dynamodb.AttributeType.STRING,
        },
        billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
        removalPolicy: environment.production
          ? cdk.RemovalPolicy.RETAIN
          : cdk.RemovalPolicy.DESTROY,
      }
    );

    this.snapshotIdParameter = new ssm.StringParameter(
      this,
      "ServerStorageSnapshotIdParameter",
      {
        stringValue: environment.production
          ? "N/A"
          : environment.server.storage.snapshotId ?? "N/A",
      }
    );
  }
}
