import os
import hydra

from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from omegaconf import OmegaConf


@dataclass
class User:
    name: str
    email: str
    password: str


@dataclass
class Storage:
    device_name: str
    device_mount_point: str
    container_mount_point: str
    snapshot_id: Optional[str] = None


@dataclass
class Environment:
    LOG_LEVEL: str
    LOGS_DIRECTORY_PATH: str
    DATABASE_FOLDER: str
    DATABASE_FILE: str
    UPLOAD_FOLDER: str
    RECAPTCHA_SITE_KEY: str
    RECAPTCHA_SECRET_KEY: str
    SNAPSHOT_LAMBDA_NAME_PARAMETER: str = "N/A"


@dataclass
class Server:
    storage: Storage
    environment_variables: Environment


@dataclass
class Testing:
    url: str
    users: list[User] = field(default_factory=list)


@dataclass
class Configuration:
    domain_name: str
    server: Server
    testing: Testing
    allowed_cidr_blocks: list[str]
    production: bool = False
    transition: dict = field(default_factory=dict)
    account: str = os.environ["CDK_DEFAULT_ACCOUNT"]
    region: str = os.environ["CDK_DEFAULT_REGION"]


configuration_store = hydra.core.config_store.ConfigStore.instance()

for configuration in Path("nitecap/configuration").glob("*.yaml"):
    configuration_store.store(
        name=configuration.name.removesuffix(".yaml"),
        node=OmegaConf.merge(
            OmegaConf.structured(Configuration),
            OmegaConf.load(configuration),
        ),
    )
