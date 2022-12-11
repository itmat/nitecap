import aws_cdk as cdk
import aws_cdk.aws_ssm as ssm

from constructs import Construct
from ...configuration import Configuration


class TransitionParameterStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        configuration: Configuration,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.snapshot_lambda_name_parameter = ssm.StringParameter(
            self, "SnapshotLambdaNameParameter", string_value="TBD"
        )

        self.previous_snapshot_id_parameter = ssm.StringParameter(
            self,
            "PreviousSnapshotIdParameter",
            string_value=configuration.previous_server_storage_snapshot_id,
        )
