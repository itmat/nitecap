#!/usr/bin/env python3

import boto3
import json
import os

from pathlib import Path

code = Path(__file__).parents[4]


with open(code / "cdk.outputs.json") as outputs:
    outputs = json.load(outputs)

for stack in outputs:
    if stack.endswith("ServerStack"):
        outputs = outputs[stack]

database = json.loads(
    boto3.client("secretsmanager").get_secret_value(
        SecretId=outputs["DatabaseSecretArn"]
    )["SecretString"]
)

configuration_file = Path.home() / ".pgpass"

with configuration_file.open("w") as configuration:
    configuration.write(
        f"{database['host']}:{database['port']}:{database['dbname']}:{database['username']}:{database['password']}"
    )


configuration_file.chmod(0o600)

os.execv(
    "/usr/bin/psql",
    [
        "--username",
        database["username"],
        "--host",
        database["host"],
        "--port",
        str(database["port"]),
        "--dbname",
        database["dbname"],
    ],
)
