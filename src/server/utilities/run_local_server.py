import argparse
import boto3
import docker
import json
import os
import subprocess

from docker.types import Mount
from pathlib import Path

code = Path(__file__).parents[3]


# Parse arguments

parser = argparse.ArgumentParser(
    description="Run development or Apache server"
)
parser.add_argument(
    "--apache", default=False, action="store_true", help="run Apache server"
)
arguments = parser.parse_args()


# Load environment variables

environment = {}

with open(code / "outputs.json") as outputs:
    outputs = json.load(outputs)

for stack in outputs:
    if stack.endswith("ServerStack"):
        outputs = outputs[stack]

for variable in outputs["EnvironmentVariables"].split():
    if variable not in os.environ:
        environment[variable] = outputs[variable.replace("_", "")]

if "SECRET_KEY" not in os.environ:
    environment["SECRET_KEY"] = "SECRET_KEY"

environment["ENV"] = "PROD" if arguments.apache else "DEV"


# Retrieve AWS credentials

session = boto3.session.Session()
credentials = session.get_credentials()

environment["AWS_ACCESS_KEY_ID"] = credentials.access_key
environment["AWS_SECRET_ACCESS_KEY"] = credentials.secret_key
environment["AWS_DEFAULT_REGION"] = session.region_name


SERVER = "nitecap"

if not arguments.apache:
    # Adjust the ownership of stored files
    subprocess.run(f"sudo chown -R vscode:vscode {os.environ['STORAGE']}", shell=True)

    # Adjust paths of directories which hold data
    for directory in ("DATABASE_FOLDER", "LOGS_DIRECTORY_PATH", "UPLOAD_FOLDER"):
        path = Path(environment[directory])
        path = os.environ["STORAGE"] / path.relative_to("/nitecap_web")
        path.mkdir(exist_ok=True)

        environment[directory] = path

    # Run the development server
    try:
        subprocess.run(
            f"python3 app.py",
            cwd=code / "src/server",
            env=os.environ | environment,
            shell=True,
        )
    except KeyboardInterrupt:
        pass
else:
    client = docker.DockerClient()

    # Find storage volume
    development_container = client.containers.get(os.environ["HOSTNAME"])

    for mount in development_container.attrs["Mounts"]:
        if mount["Destination"] == os.environ["STORAGE"]:
            storage = client.volumes.get(mount["Name"])

    # Adjust the ownership of stored files
    subprocess.run(f"sudo chown -R 1001:1001 {os.environ['STORAGE']}", shell=True)

    # Stop and remove existing container
    try:
        container = client.containers.get(SERVER)
    except docker.errors.NotFound:
        pass
    else:
        if container.status != "exited":
            container.stop()
        container.remove()

    # Build image and create container
    image, _ = client.images.build(path=str(code / "src/server"))

    container = client.containers.create(
        image,
        name=SERVER,
        mounts=[Mount("/nitecap_web", storage.id)],
        ports={"5000/tcp": 5000},
        environment=environment,
    )

    container.start()
    print("The server is listening on port five thousand...")

    try:
        container.wait()
    except KeyboardInterrupt:
        container.stop()
