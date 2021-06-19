import * as cdk from "@aws-cdk/core";
import * as route53 from "@aws-cdk/aws-route53";

import { parseDomain, ParseResultType } from "parse-domain";
import { Environment } from "./environment";

type DomainStackProps = cdk.StackProps & { environment: Environment };

export class DomainStack extends cdk.Stack {
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

    this.hostedZone = route53.HostedZone.fromLookup(this, "HostedZone", {
      domainName: this.domainName,
    });
  }
}
