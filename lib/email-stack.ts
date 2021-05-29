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

import toPascalCase from "./utilities/toPascalCase";

function normalize(name: string) {
  return name.replace(/\./g, "_");
}

type EmailStackProps = cdk.StackProps & {
  domainName: string;
  subdomainName: string;
  hostedZone: route53.IHostedZone;
  emailSuppressionList: dynamodb.Table;
};

export class EmailStack extends cdk.Stack {
  readonly configurationSetName: string;

  constructor(scope: cdk.Construct, id: string, props: EmailStackProps) {
    super(scope, id, props);

    // Compliance

    let bouncesTopic = new sns.Topic(this, "BouncesTopic");
    let complaintsTopics = new sns.Topic(this, "ComplaintsTopics");

    let bouncesLambda = new lambda.Function(this, "BouncesLambda", {
      code: lambda.Code.fromAsset(path.join(__dirname, "compliance")),
      handler: "bounces.handler",
      runtime: lambda.Runtime.PYTHON_3_8,
      environment: {
        SOFT_BOUNCES_RECIPIENT: `admins@${props.domainName}`,
        EMAIL_SUPPRESSION_LIST_NAME: props.emailSuppressionList.tableName,
      },
    });

    props.emailSuppressionList.grantWriteData(bouncesLambda);

    bouncesLambda.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["ses:SendEmail"],
        resources: [
          `arn:${this.partition}:ses:${this.region}:${this.account}:identity/admins@${props.domainName}`,
        ],
      })
    );

    bouncesTopic.addSubscription(
      new subscriptions.LambdaSubscription(bouncesLambda)
    );

    complaintsTopics.addSubscription(
      new subscriptions.EmailSubscription(`admins@${props.domainName}`)
    );

    // Configuration

    let configurationSet = new ses.CfnConfigurationSet(
      this,
      "ConfigurationSet",
      { name: `ConfigurationSet-${normalize(props.subdomainName)}` }
    );

    if (!configurationSet.name) {
      throw Error("Email configuration set does not have a name");
    }

    this.configurationSetName = configurationSet.name;

    let configuration = {
      bounce: bouncesTopic,
      complaint: complaintsTopics,
    };

    for (let [eventType, destination] of Object.entries(configuration)) {
      new cr.AwsCustomResource(
        this,
        `Email${toPascalCase(eventType)}Destination`,
        {
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
              EventDestinationName: `Topic-${destination.node.addr}`,
              EventDestination: {
                Enabled: true,
                MatchingEventTypes: [eventType.toUpperCase()],
                SnsDestination: {
                  TopicArn: destination.topicArn,
                },
              },
            },
            physicalResourceId: cr.PhysicalResourceId.of(destination.topicArn),
          },
        }
      );
    }

    let emailIdentity = new cr.AwsCustomResource(this, "EmailIdentity", {
      policy: {
        statements: [
          new iam.PolicyStatement({
            effect: iam.Effect.ALLOW,
            actions: ["ses:CreateEmailIdentity", "ses:DeleteEmailIdentity"],
            resources: [
              `arn:${this.partition}:ses:${this.region}:${this.account}:identity/${props.subdomainName}`,
            ],
          }),
        ],
      },
      onUpdate: {
        service: "SESV2",
        action: "createEmailIdentity",
        parameters: {
          EmailIdentity: props.subdomainName,
          ConfigurationSetName: this.configurationSetName,
        },
        physicalResourceId: cr.PhysicalResourceId.of(this.stackId),
      },
      onDelete: {
        service: "SESV2",
        action: "deleteEmailIdentity",
        parameters: {
          EmailIdentity: props.subdomainName,
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
          zone: props.hostedZone,
          recordName: `${token}._domainkey.${props.subdomainName}`,
          domainName: `${token}.dkim.amazonses.com`,
        })
    );
  }
}
