import tldextract

import aws_cdk as cdk
import aws_cdk.aws_route53 as route53

from constructs import Construct
from .configuration import Configuration


class DomainStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        configuration: Configuration,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        subdomain, domain, suffix = tldextract.extract(configuration.domain_name)
        
        self.hosted_zone = route53.HostedZone.from_lookup(
            self,
            "HostedZone",
            domain_name=f"{domain}.{suffix}",
        )
