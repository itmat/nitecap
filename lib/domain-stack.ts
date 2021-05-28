import * as acm from "@aws-cdk/aws-certificatemanager";
import * as cdk from "@aws-cdk/core";
import * as route53 from "@aws-cdk/aws-route53";

import { parseDomain, ParseResultType } from "parse-domain";
import { Environment } from "./environment";

type DomainStackProps = cdk.StackProps & { environment: Environment };

export class DomainStack extends cdk.Stack {
  readonly certificate: acm.Certificate;
  readonly domainName: string;
  readonly subdomainName: string;
  readonly hostedZone: route53.IHostedZone;

  constructor(scope: cdk.Construct, id: string, props: DomainStackProps) {
    super(scope, id, props);

    let parseResult = parseDomain(props.environment.subdomainName);
    if (parseResult.type !== ParseResultType.Listed)
      throw Error("Invalid subdomain name");

    let { domain, topLevelDomains } = parseResult;
    this.domainName = `${domain}.${topLevelDomains.join(".")}`;
    this.subdomainName = props.environment.subdomainName;

    let mainHostedZone = route53.HostedZone.fromLookup(this, "MainHostedZone", {
      domainName: this.domainName,
    });

    if (this.subdomainName === this.domainName)
      this.hostedZone = mainHostedZone;
    else {
      this.hostedZone = new route53.HostedZone(this, "HostedZone", {
        zoneName: this.subdomainName,
      });

      if (!this.hostedZone.hostedZoneNameServers)
        throw Error("Invalid hosted zone");

      new route53.NsRecord(this, "NsRecord", {
        zone: mainHostedZone,
        recordName: this.subdomainName,
        values: this.hostedZone.hostedZoneNameServers,
      });
    }

    this.certificate = new acm.DnsValidatedCertificate(this, "Certificate", {
      hostedZone: this.hostedZone,
      domainName: this.subdomainName,
    });
  }
}
