import pymxbi
from loguru import logger
from pymxbi import MXBI, MXBIModel

from .config_store import ConfigStore
from .models.session import SessionConfig


def build_mxbi(mxbi_config_path, session_config_path) -> MXBI:

    mxbi_config = ConfigStore(mxbi_config_path, MXBIModel).value
    session_config = ConfigStore(session_config_path, SessionConfig).value

    mxbi = pymxbi.build_mxbi(mxbi_config, logger)
    mxbi.register_animal(
        {animal.rfid_id: animal.name for animal in session_config.animals}
    )

    return mxbi
