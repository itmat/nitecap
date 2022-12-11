import aws_cdk as core
import aws_cdk.assertions as assertions

from nitecap.nitecap_stack import NitecapStack

# example tests. To run these tests, uncomment this file along with the example
# resource in nitecap/nitecap_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = NitecapStack(app, "nitecap")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
