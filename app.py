#!/usr/bin/env python3
import hydra
import aws_cdk as cdk

from nitecap.configuration import Configuration
from nitecap.domain_stack import DomainStack
from nitecap.persistent_storage_stack import PersistentStorageStack
from nitecap.email_stack import EmailStack
from nitecap.computation_stack import ComputationStack
from nitecap.server_stack import ServerStack
from nitecap.operation_stack import OperationStack

from nitecap.utilities.transition.parameter_stack import TransitionParameterStack
from nitecap.utilities.transition.transition_stack import TransitionStack

app = cdk.App()
configuration_name = app.node.try_get_context("configuration")


@hydra.main(version_base=None, config_name=configuration_name)
def main(configuration: Configuration):

    stage = cdk.Stage(
        app,
        f"Nitecap{configuration_name.capitalize()}",
        env={
            "region": configuration.region,
            "account": configuration.account,
        },
    )

    domain_stack = DomainStack(stage, "DomainStack", configuration=configuration)

    persistent_storage_stack = PersistentStorageStack(
        stage, "PersistentStorageStack", configuration=configuration
    )

    email_stack = EmailStack(
        stage,
        "EmailStack",
        configuration=configuration,
        email_suppression_list=persistent_storage_stack.email_suppression_list,
        hosted_zone=domain_stack.hosted_zone,
    )

    computation_stack = ComputationStack(
        stage,
        "ComputationStack",
        spreadsheet_bucket=persistent_storage_stack.spreadsheet_bucket,
    )

    server_stack_arguments = dict(
        configuration=configuration,
        computation_state_machine=computation_stack.computation_state_machine,
        email_suppression_list=persistent_storage_stack.email_suppression_list,
        notification_api=computation_stack.notification_api,
        hosted_zone=domain_stack.hosted_zone,
        snapshot_id_parameter=persistent_storage_stack.snapshot_id_parameter,
        email_configuration_set_name=email_stack.configuration_set_name,
        spreadsheet_bucket=persistent_storage_stack.spreadsheet_bucket,
        storage_bucket=persistent_storage_stack.storage_bucket,
    )

    if configuration.transition:
        TransitionStack(
            stage,
            "TransitionStack",
            **server_stack_arguments,
            parameters=TransitionParameterStack(
                stage, "TransitionParameterStack", configuration=configuration
            ),
        )

    server_stack = ServerStack(stage, "ServerStack", **server_stack_arguments)

    if configuration.production:
        OperationStack(
            stage,
            "OperationStack",
            configuration=configuration,
            domain_stack=domain_stack,
            persistent_storage_stack=persistent_storage_stack,
            email_stack=email_stack,
            computation_stack=computation_stack,
            server_stack=server_stack,
        )

    app.synth()


if __name__ == "__main__":
    main()
