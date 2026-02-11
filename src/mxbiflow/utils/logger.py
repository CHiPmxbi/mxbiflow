import sys

from loguru import logger

from ..core.path import get_log_path

logger.remove()

logger.add(sys.stderr, level="DEBUG")


def init_logger() -> None:
    logger.add(
        f"{get_log_path()}/mxbi.log",
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        encoding="utf-8",
        level="DEBUG",
        serialize=True,
    )
