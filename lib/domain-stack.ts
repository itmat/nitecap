import * as acm from "@aws-cdk/aws-certificatemanager";
import * as cdk from "@aws-cdk/core";
import * as route53 from "@aws-cdk/aws-route53";

import * as environment from "./.env.json";

export class DomainStack extends cdk.Stack {
  readonly certificate: acm.Certificate;
  readonly domainName: string;
  readonly hostedZone: route53.IHostedZone;

  constructor(scope: cdk.Construct, id: string, props: cdk.StackProps) {
    super(scope, id, props);

    this.domainName = environment.domainName;

    this.hostedZone = route53.HostedZone.fromHostedZoneAttributes(
      this,
      "HostedZone",
      environment.hostedZoneAttributes
    );

    this.certificate = new acm.DnsValidatedCertificate(this, "Certificate", {
      hostedZone: this.hostedZone,
      domainName: this.domainName,
    });
  }
}
