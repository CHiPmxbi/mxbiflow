import pymxbi
from loguru import logger
from pymxbi import MXBI, MXBIModel

from .config_store import ConfigStore
from .path import get_mxbi_config_path


def build_mxbi() -> MXBI:

    mxbi_config = ConfigStore(get_mxbi_config_path(), MXBIModel).value

    mxbi = pymxbi.build_mxbi(mxbi_config, logger)

    return mxbi
