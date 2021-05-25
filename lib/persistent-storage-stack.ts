import * as autoscaling from "@aws-cdk/aws-autoscaling";
import * as cdk from "@aws-cdk/core";
import * as dynamodb from "@aws-cdk/aws-dynamodb";
import * as s3 from "@aws-cdk/aws-s3";

import * as environment from "./.env.json";
export class PersistentStorageStack extends cdk.Stack {
  readonly spreadsheetBucket: s3.Bucket;
  readonly emailSuppressionList: dynamodb.Table;
  readonly serverBlockDevice: autoscaling.BlockDevice;

  constructor(
    scope: cdk.Construct,
    id: string,
    props: cdk.StackProps & { domainName: string }
  ) {
    super(scope, id, props);

    const { domainName } = props;

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
          allowedOrigins: [`https://${domainName}`, "http://localhost:5000"],
        },
      ],
      autoDeleteObjects: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
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
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }
    );

    this.serverBlockDevice = {
      deviceName: environment.server.storage.deviceName,
      volume: autoscaling.BlockDeviceVolume.ebsFromSnapshot(
        environment.server.storage.snapshotId,
        {
          deleteOnTermination: environment.production ? false : true,
        }
      ),
    };
  }
}
