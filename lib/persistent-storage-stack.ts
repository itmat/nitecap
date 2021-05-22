import * as cdk from "@aws-cdk/core";
import * as s3 from "@aws-cdk/aws-s3";

export class PersistentStorageStack extends cdk.Stack {
  readonly spreadsheetBucket: s3.Bucket;

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
  }
}
