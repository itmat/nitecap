import argparse
import boto3
import docker
import json
import os

from docker.types import Mount
from glob import glob
from pathlib import Path

code = Path(__file__).parents[3]


# Parse arguments

parser = argparse.ArgumentParser(description="Run development or Apache server")
parser.add_argument(
    "--apache", default=False, action="store_true", help="run Apache server"
)
arguments = parser.parse_args()


# Load environment variables

environment = {}

with open(code / "cdk.outputs.json") as outputs:
    outputs = json.load(outputs)

for stack in outputs:
    if stack.endswith("ServerStack"):
        outputs = outputs[stack]

for variable in outputs["EnvironmentVariables"].split():
    environment[variable] = outputs[variable.replace("_", "")]

environment["SECRET_KEY"] = "SECRET_KEY"
environment["ENV"] = "PROD" if arguments.apache else "DEV"


# Retrieve AWS credentials

session = boto3.session.Session()
credentials = session.get_credentials()

environment["AWS_ACCESS_KEY_ID"] = credentials.access_key
environment["AWS_SECRET_ACCESS_KEY"] = credentials.secret_key


SERVER = "nitecap"
client = docker.DockerClient()

# Find storage volume

development_container = client.containers.get(os.environ["HOSTNAME"])

for mount in development_container.attrs["Mounts"]:
    if mount["Destination"] == os.environ["STORAGE"]:
        volume = client.volumes.get(mount["Name"])
        storage = Mount("/nitecap_web", volume.id)


# Find workspaces mount

for mount in development_container.attrs["Mounts"]:
    if mount["Destination"].startswith("/workspaces"):
        if mount["Type"] == "bind":
            workspaces = Mount(mount["Destination"], mount["Source"], type="bind")
        if mount["Type"] == "volume":
            volume = client.volumes.get(mount["Name"])
            workspaces = Mount("/workspaces", volume.id)


# Stop and remove existing container

try:
    container = client.containers.get(SERVER)
except docker.errors.NotFound:
    pass
else:
    if container.status != "exited":
        container.stop()
    container.remove()


# Create a new container

configuration = dict(mounts=[storage])

if arguments.apache:
    image, _ = client.images.build(path=str(code / "nitecap/server"))
else:
    image = client.images.get(development_container.attrs["Image"])
    environment = os.environ | environment
    configuration["mounts"].append(workspaces)
    configuration["command"] = "python3 app.py"
    configuration["working_dir"] = glob("/workspaces/*/nitecap/server").pop()

container = client.containers.create(
    image,
    name=SERVER,
    ports={"5000/tcp": 5000},
    environment=environment,
    **configuration,
)


# Run the container

container.start()
print("The server is listening on port five thousand...")

try:
    for line in map(bytes.decode, container.logs(stream=True)):
        print(line.removesuffix("\n"))
except KeyboardInterrupt:
    container.stop()
