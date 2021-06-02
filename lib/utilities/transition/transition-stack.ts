import * as cdk from "@aws-cdk/core";
import * as cr from "@aws-cdk/custom-resources";
import * as iam from "@aws-cdk/aws-iam";
import * as lambda from "@aws-cdk/aws-lambda";

import * as path from "path";

import { TransitionParameterStack } from "./parameter-stack";
import { ServerStack, ServerStackProps } from "../../server-stack";

type TransitionStackProps = cdk.StackProps & {
  serverStackProps: ServerStackProps;
  parameters: TransitionParameterStack;
};

export class TransitionStack extends cdk.Stack {
  constructor(scope: cdk.Construct, id: string, props: TransitionStackProps) {
    super(scope, id, props);

    // Server used to make the transition

    let { environment, ...serverStackPropsWithoutEnvironment } =
      props.serverStackProps;

    let transitionServerProps: ServerStackProps = {
      environment: JSON.parse(JSON.stringify(environment)),     // deep copy
      ...serverStackPropsWithoutEnvironment,
    };

    transitionServerProps.subdomainName = `transition.${props.serverStackProps.subdomainName}`;
    transitionServerProps.snapshotIdParameter =
      props.parameters.previousSnapshotIdParameter;
    transitionServerProps.environment.server.variables.SNAPSHOT_LAMBDA_NAME_PARAMETER =
      props.parameters.snapshotLambdaNameParameter.parameterName;

    let transitionServerStack = new ServerStack(this, "TransitionServerStack", {
      ...transitionServerProps,
      applicationDockerfile: "utilities/transition/Dockerfile",
      additionalPermissions: [
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: ["ssm:GetParameter"],
          resources: [
            props.parameters.snapshotLambdaNameParameter.parameterArn,
          ],
        }),
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: ["lambda:InvokeFunction"],
          resources: ["*"],
        }),
      ],
    });

    // Snapshot taking lambda

    let transitionWaitConditionHandle = new cdk.CfnWaitConditionHandle(
      this,
      "TransitionWaitConditionHandle"
    );

    let snapshotLambda = new lambda.Function(this, "SnapshotLambda", {
      code: lambda.Code.fromAsset(path.join(__dirname, ".")),
      handler: "take_snapshot.handler",
      runtime: lambda.Runtime.PYTHON_3_8,
      timeout: cdk.Duration.minutes(15),
      environment: {
        SNAPSHOT_ID_PARAMETER_NAME:
          props.serverStackProps.snapshotIdParameter.parameterName,
        TRANSITION_SERVER_INSTANCE_ID:
          transitionServerStack.containerInstance.instanceId,
        TRANSITION_SERVER_BLOCK_STORAGE_ID:
          transitionServerStack.containerInstance.volumeId,
        WAIT_CONDITION_HANDLE_URL: transitionWaitConditionHandle.ref,
      },
    });

    let queryPolicy = new iam.PolicyStatement();
    queryPolicy.addActions("ec2:DescribeInstances", "ec2:DescribeSnapshots");
    queryPolicy.addResources("*");

    let terminateInstancePolicy = new iam.PolicyStatement();
    terminateInstancePolicy.addActions("ec2:TerminateInstances");
    terminateInstancePolicy.addResources(
      `arn:${this.partition}:ec2:${this.region}:${this.account}:instance/${transitionServerStack.containerInstance.instanceId}`
    );

    let createSnapshotPolicy = new iam.PolicyStatement();
    createSnapshotPolicy.addActions("ec2:CreateSnapshot");
    createSnapshotPolicy.addResources(
      `arn:${this.partition}:ec2:${this.region}::snapshot/*`,
      `arn:${this.partition}:ec2:${this.region}:${this.account}:volume/${transitionServerStack.containerInstance.volumeId}`
    );

    for (let policy of [
      queryPolicy,
      terminateInstancePolicy,
      createSnapshotPolicy,
    ])
      snapshotLambda.addToRolePolicy(policy);

    props.serverStackProps.snapshotIdParameter.grantWrite(snapshotLambda);

    let putSnapshotLambdaNameParameter = new cr.AwsCustomResource(
      this,
      "PutSnapshotLambdaNameParameter",
      {
        policy: {
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: ["ssm:PutParameter"],
              resources: [
                props.parameters.snapshotLambdaNameParameter.parameterArn,
              ],
            }),
          ],
        },
        onUpdate: {
          service: "SSM",
          action: "putParameter",
          parameters: {
            Name: props.parameters.snapshotLambdaNameParameter.parameterName,
            Value: snapshotLambda.functionName,
            Overwrite: true,
          },
          physicalResourceId: cr.PhysicalResourceId.of(
            snapshotLambda.functionArn
          ),
        },
      }
    );

    let transitionWaitCondition = new cdk.CfnWaitCondition(
      this,
      "TransitionWaitCondition",
      {
        count: 1,
        handle: transitionWaitConditionHandle.ref,
        timeout: "43200",
      }
    );

    transitionWaitCondition.addDependsOn(
      putSnapshotLambdaNameParameter.node.defaultChild?.node._actualNode
        .defaultChild as cdk.CfnResource
    );
  }
}
