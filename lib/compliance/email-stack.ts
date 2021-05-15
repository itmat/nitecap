import * as cdk from "@aws-cdk/core";
import * as dynamodb from "@aws-cdk/aws-dynamodb";
import * as lambda from "@aws-cdk/aws-lambda";
import * as iam from "@aws-cdk/aws-iam";
import * as sns from "@aws-cdk/aws-sns";
import * as subscriptions from "@aws-cdk/aws-sns-subscriptions";

import * as path from "path";

const BOUNCES_DESTINATION_EMAIL = "nitebelt@gmail.com";
const COMPLAINTS_DESTINATION_EMAIL = "nitebelt@gmail.com";

export class EmailStack extends cdk.Stack {
  readonly emailSuppressionList: dynamodb.Table;
  
  constructor(scope: cdk.Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

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

    let bouncesTopic = new sns.Topic(this, "BouncesTopic");
    let complaintsTopics = new sns.Topic(this, "ComplaintsTopics");

    let bouncesLambda = new lambda.Function(this, "BouncesLambda", {
      code: lambda.Code.fromAsset(path.join(__dirname, "destinations")),
      handler: "bounces.handler",
      runtime: lambda.Runtime.PYTHON_3_8,
      environment: {
        BOUNCES_DESTINATION_EMAIL,
        EMAIL_SUPPRESSION_LIST_NAME: this.emailSuppressionList.tableName,
      },
    });

    this.emailSuppressionList.grantWriteData(bouncesLambda);

    bouncesLambda.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["ses:SendEmail"],
        resources: [
          `arn:${this.partition}:ses:${this.region}:${this.account}:identity/${BOUNCES_DESTINATION_EMAIL}`,
        ],
      })
    );

    bouncesTopic.addSubscription(
      new subscriptions.LambdaSubscription(bouncesLambda)
    );

    complaintsTopics.addSubscription(
      new subscriptions.EmailSubscription(COMPLAINTS_DESTINATION_EMAIL)
    );
  }
}
