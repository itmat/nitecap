import * as cdk from "@aws-cdk/core";
import * as cr from "@aws-cdk/custom-resources";
import * as dynamodb from "@aws-cdk/aws-dynamodb";
import * as lambda from "@aws-cdk/aws-lambda";
import * as iam from "@aws-cdk/aws-iam";
import * as route53 from "@aws-cdk/aws-route53";
import * as ses from "@aws-cdk/aws-ses";
import * as sns from "@aws-cdk/aws-sns";
import * as subscriptions from "@aws-cdk/aws-sns-subscriptions";

import * as path from "path";

const BOUNCES_DESTINATION_EMAIL = "nitebelt@gmail.com";
const COMPLAINTS_DESTINATION_EMAIL = "nitebelt@gmail.com";

function normalize(name: string) {
  return name.replace(/\./g, "_");
}

export class EmailStack extends cdk.Stack {
  readonly configurationSetName: string;

  constructor(
    scope: cdk.Construct,
    id: string,
    props: cdk.StackProps & {
      domainName: string;
      hostedZone: route53.IHostedZone;
      emailSuppressionListArn: string;
    }
  ) {
    super(scope, id, props);

    const { domainName, hostedZone, emailSuppressionListArn } = props;

    // Compliance

    let emailSuppressionList = dynamodb.Table.fromTableArn(
      this,
      "EmailSuppressionList",
      emailSuppressionListArn
    );

    let bouncesTopic = new sns.Topic(this, "BouncesTopic");
    let complaintsTopics = new sns.Topic(this, "ComplaintsTopics");

    let bouncesLambda = new lambda.Function(this, "BouncesLambda", {
      code: lambda.Code.fromAsset(
        path.join(__dirname, "compliance/destinations")
      ),
      handler: "bounces.handler",
      runtime: lambda.Runtime.PYTHON_3_8,
      environment: {
        BOUNCES_DESTINATION_EMAIL,
        EMAIL_SUPPRESSION_LIST_NAME: emailSuppressionList.tableName,
      },
    });

    emailSuppressionList.grantWriteData(bouncesLambda);

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

    // Configuration

    let configurationSet = new ses.CfnConfigurationSet(
      this,
      "ConfigurationSet",
      { name: `ConfigurationSet-${normalize(domainName)}` }
    );

    if (!configurationSet.name) {
      throw Error("Email configuration set does not have a name");
    }

    this.configurationSetName = configurationSet.name;

    let configuration = {
      Bounce: {
        eventTypes: ["BOUNCE"],
        topic: bouncesTopic,
      },
      Complaint: {
        eventTypes: ["COMPLAINT"],
        topic: complaintsTopics,
      },
    };

    for (let [eventType, destination] of Object.entries(configuration)) {
      new cr.AwsCustomResource(this, `Email${eventType}Destination`, {
        policy: {
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: ["ses:CreateConfigurationSetEventDestination"],
              resources: [
                `arn:${this.partition}:ses:${this.region}:${this.account}:configuration-set/${this.configurationSetName}`,
              ],
            }),
          ],
        },
        onUpdate: {
          service: "SESV2",
          action: "createConfigurationSetEventDestination",
          parameters: {
            ConfigurationSetName: this.configurationSetName,
            EventDestinationName: `Topic-${destination.topic.node.addr}`,
            EventDestination: {
              Enabled: true,
              MatchingEventTypes: destination.eventTypes,
              SnsDestination: {
                TopicArn: destination.topic.topicArn,
              },
            },
          },
          physicalResourceId: cr.PhysicalResourceId.of(
            destination.topic.topicArn
          ),
        },
      });
    }

    let emailIdentity = new cr.AwsCustomResource(this, "EmailIdentity", {
      policy: {
        statements: [
          new iam.PolicyStatement({
            effect: iam.Effect.ALLOW,
            actions: ["ses:CreateEmailIdentity", "ses:DeleteEmailIdentity"],
            resources: [
              `arn:${this.partition}:ses:${this.region}:${this.account}:identity/${domainName}`,
            ],
          }),
        ],
      },
      onUpdate: {
        service: "SESV2",
        action: "createEmailIdentity",
        parameters: {
          EmailIdentity: domainName,
          ConfigurationSetName: this.configurationSetName,
        },
        physicalResourceId: cr.PhysicalResourceId.of(this.stackId),
      },
      onDelete: {
        service: "SESV2",
        action: "deleteEmailIdentity",
        parameters: {
          EmailIdentity: domainName,
        },
      },
    });

    let tokenIndices = [0, 1, 2];
    let domainKeysIdentifiedMailTokens = tokenIndices.map((tokenIndex) =>
      emailIdentity.getResponseField(`DkimAttributes.Tokens.${tokenIndex}`)
    );

    domainKeysIdentifiedMailTokens.map(
      (token, i) =>
        new route53.CnameRecord(this, `DomainKeysIdentifiedMailRecord-${i}`, {
          zone: hostedZone,
          recordName: `${token}._domainkey.${domainName}`,
          domainName: `${token}.dkim.amazonses.com`,
        })
    );
  }
}
