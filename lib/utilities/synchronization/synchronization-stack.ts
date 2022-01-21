import * as cdk from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";

import { Construct } from "constructs";

import { ServerStack, ServerStackProps } from "../../server-stack";
import { sourceBucketName } from "./.env";

export class SynchronizationStack extends cdk.Stack {
  constructor(
    scope: Construct,
    id: string,
    props: cdk.StackProps & { serverStackProps: ServerStackProps }
  ) {
    super(scope, id, props);

    // Stack used to copy and synchronize data between buckets and other data sources

    let { environment, ...serverStackPropsWithoutEnvironment } =
      props.serverStackProps;

    let synchronizationServerProps: ServerStackProps = {
      environment: JSON.parse(JSON.stringify(environment)), // deep copy
      ...serverStackPropsWithoutEnvironment,
    };

    synchronizationServerProps.subdomainName = `synchronization.${props.serverStackProps.subdomainName}`;
    synchronizationServerProps.environment.server.variables.SOURCE_BUCKET_NAME =
      sourceBucketName;

    new ServerStack(this, "SynchronizationServerStack", {
      ...synchronizationServerProps,
      applicationDockerfile: "utilities/synchronization/Dockerfile",
      additionalPermissions: [
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: ["s3:ListBucket", "s3:GetObject"],
          resources: [
            `arn:${this.partition}:s3:::${sourceBucketName}`,
            `arn:${this.partition}:s3:::${sourceBucketName}/*`,
          ],
        }),
      ],
    });
  }
}
