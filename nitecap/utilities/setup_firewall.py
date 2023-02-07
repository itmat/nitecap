import aws_cdk.aws_elasticloadbalancingv2 as elb
import aws_cdk.aws_wafv2 as waf


def setup_firewall(load_balancer: elb.ApplicationLoadBalancer):
    def managed_rule(name, priority, excluded_rules=[], **configuration):
        return waf.CfnWebACL.RuleProperty(
            name=f"{load_balancer.stack.stack_name}{name}",
            priority=priority,
            statement=waf.CfnWebACL.StatementProperty(
                managed_rule_group_statement=waf.CfnWebACL.ManagedRuleGroupStatementProperty(
                    name=f"AWSManagedRules{name}",
                    vendor_name="AWS",
                    excluded_rules=[
                        waf.CfnWebACL.ExcludedRuleProperty(name=excluded_rule)
                        for excluded_rule in excluded_rules
                    ],
                    **configuration,
                )
            ),
            override_action=waf.CfnWebACL.OverrideActionProperty(none={}),
            visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                metric_name=f"{name}Metric",
                cloud_watch_metrics_enabled=True,
                sampled_requests_enabled=True,
            ),
        )

    admin_protection_rule_set = managed_rule("AdminProtectionRuleSet", priority=1)
    ip_reputation_list = managed_rule("AmazonIpReputationList", priority=2)
    common_rule_set = managed_rule(
        "CommonRuleSet", priority=3, excluded_rules=["SizeRestrictions_BODY"]
    )
    linux_rule_set = managed_rule("LinuxRuleSet", priority=4)
    unix_rule_set = managed_rule("UnixRuleSet", priority=5)
    sql_injection_rule_set = managed_rule("SQLiRuleSet", priority=6)

    web_acl = waf.CfnWebACL(
        load_balancer.stack,
        f"{load_balancer.stack.stack_name}ACL",
        scope="REGIONAL",
        rules=[
            admin_protection_rule_set,
            ip_reputation_list,
            common_rule_set,
            linux_rule_set,
            unix_rule_set,
            sql_injection_rule_set,
        ],
        default_action=waf.CfnWebACL.DefaultActionProperty(
            allow=waf.CfnWebACL.AllowActionProperty()
        ),
        visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
            metric_name="ACL",
            cloud_watch_metrics_enabled=True,
            sampled_requests_enabled=True,
        ),
    )

    waf.CfnWebACLAssociation(
        load_balancer.stack,
        "LoadBalancerFirewall",
        web_acl_arn=web_acl.attr_arn,
        resource_arn=load_balancer.load_balancer_arn,
    )
