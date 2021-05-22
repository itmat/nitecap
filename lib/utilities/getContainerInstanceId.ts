import * as cdk from "@aws-cdk/core";
import * as cr from "@aws-cdk/custom-resources";
import * as ecs from "@aws-cdk/aws-ecs";
import * as iam from "@aws-cdk/aws-iam";

export default function getContainerInstanceId(
  stack: cdk.Stack,
  cluster: ecs.Cluster
) {

  let clusterContainerInstancesList = new cr.AwsCustomResource(
    stack,
    "ClusterContainerInstancesList",
    {
      policy: {
        statements: [
          new iam.PolicyStatement({
            effect: iam.Effect.ALLOW,
            actions: ["ecs:ListContainerInstances"],
            resources: [cluster.clusterArn]
          }),
        ],
      },
      onUpdate: {
        service: "ECS",
        action: "listContainerInstances",
        parameters: {
          cluster: cluster.clusterArn,
        },
        physicalResourceId: cr.PhysicalResourceId.of(cluster.clusterArn),
      },
    }
  );

  clusterContainerInstancesList.node.addDependency(cluster);

  let containerInstanceArn = clusterContainerInstancesList.getResponseField(
    "containerInstanceArns.0"
  );

  let clusterContainerInstancesDescriptions = new cr.AwsCustomResource(
    stack,
    "ClusterContainerInstancesDescriptions",
    {
      policy: {
        statements: [
          new iam.PolicyStatement({
            effect: iam.Effect.ALLOW,
            actions: ["ecs:DescribeContainerInstances"],
            resources: [containerInstanceArn]
          }),
        ],
      },
      onUpdate: {
        service: "ECS",
        action: "describeContainerInstances",
        parameters: {
          cluster: cluster.clusterArn,
          containerInstances: [containerInstanceArn],
        },
        physicalResourceId: cr.PhysicalResourceId.of(containerInstanceArn),
        outputPath: "containerInstances.0.ec2InstanceId",
      },
    }
  );

  let containerInstanceId =
    clusterContainerInstancesDescriptions.getResponseField(
      "containerInstances.0.ec2InstanceId"
    );

  return containerInstanceId;
}
