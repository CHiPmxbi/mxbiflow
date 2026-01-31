import sys

from loguru import logger

from mxbi.path import LOG_PATH

logger.remove()

logger.add(sys.stderr, level="DEBUG")

logger.add(
    f"{LOG_PATH}/mxbi.log",
    rotation="10 MB",
    retention="7 days",
    compression="zip",
    encoding="utf-8",
    level="DEBUG",
    serialize=True,
)
