import pymxbi
from loguru import logger
from pymxbi import MXBI, MXBIModel

from .config_store import ConfigStore


def build_mxbi(mxbi_config_path) -> MXBI:

    mxbi_config = ConfigStore(mxbi_config_path, MXBIModel).value

    mxbi = pymxbi.build_mxbi(mxbi_config, logger)

    return mxbi
