import aws_cdk as cdk
import aws_cdk.aws_backup as backup
import aws_cdk.aws_dynamodb as dynamodb
import aws_cdk.aws_s3 as s3
import aws_cdk.aws_ssm as ssm

from constructs import Construct
from .configuration import Configuration


class PersistentStorageStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        configuration: Configuration,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        if configuration.production:
            removal_policy = cdk.RemovalPolicy.RETAIN
        else:
            removal_policy = cdk.RemovalPolicy.DESTROY

        allowed_cors_origin = [f"https://{configuration.domain_name}"]

        if not configuration.production:
            allowed_cors_origin.append("http://localhost:5000")

        self.spreadsheet_bucket = s3.Bucket(
            self,
            "SpreadsheetBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            lifecycle_rules=[
                s3.LifecycleRule(
                    transitions=[
                        s3.Transition(
                            transition_after=cdk.Duration.days(90),
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                        )
                    ]
                )
            ],
            cors=[
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.GET],
                    allowed_origins=allowed_cors_origin,
                )
            ],
            auto_delete_objects=False if configuration.production else True,
            removal_policy=removal_policy,
        )

        self.email_suppression_list = dynamodb.Table(
            self,
            "EmailSuppressionList",
            partition_key={
                "name": "email",
                "type": dynamodb.AttributeType.STRING,
            },
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=removal_policy,
        )

        self.snapshot_id_parameter = ssm.StringParameter(
            self,
            "ServerStorageSnapshotIdParameter",
            string_value=configuration.server.storage.snapshot_id or "N/A",
        )

        self.backup_vault = backup.BackupVault(
            self,
            "BackupVault",
            removal_policy=removal_policy,
        )
