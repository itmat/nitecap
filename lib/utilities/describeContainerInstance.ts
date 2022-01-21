import * as cdk from "aws-cdk-lib";
import * as cr from "aws-cdk-lib/custom-resources";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as iam from "aws-cdk-lib/aws-iam";

export default function describeContainerInstance(
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
            resources: [cluster.clusterArn],
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
            resources: [containerInstanceArn],
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
        outputPaths: ["containerInstances.0.ec2InstanceId"],
      },
    }
  );

  let containerInstanceId =
    clusterContainerInstancesDescriptions.getResponseField(
      "containerInstances.0.ec2InstanceId"
    );

  let ec2InstancesDescriptions = new cr.AwsCustomResource(
    stack,
    "Ec2InstancesDescriptions",
    {
      policy: {
        statements: [
          new iam.PolicyStatement({
            effect: iam.Effect.ALLOW,
            actions: ["ec2:DescribeInstances"],
            resources: ["*"],
          }),
        ],
      },
      onUpdate: {
        service: "EC2",
        action: "describeInstances",
        parameters: {
          InstanceIds: [containerInstanceId],
        },
        physicalResourceId: cr.PhysicalResourceId.of(containerInstanceArn),
        outputPaths:
          ["Reservations.0.Instances.0.BlockDeviceMappings.1.Ebs.VolumeId"],
      },
    }
  );

  let containerInstanceVolumeId = ec2InstancesDescriptions.getResponseField(
    "Reservations.0.Instances.0.BlockDeviceMappings.1.Ebs.VolumeId"
  );

  return {
    instanceId: containerInstanceId,
    volumeId: containerInstanceVolumeId,
  };
}
