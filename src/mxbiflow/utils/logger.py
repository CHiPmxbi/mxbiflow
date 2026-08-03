"""Logging utilities for mxbiflow.

mxbiflow is a library, so it never configures logging by itself: log
records are emitted through the standard library ``logging`` framework
and stay silent until the host application configures them.

For a batteries-included setup, call :func:`setup_logging` once, then
use loguru directly::

    from loguru import logger
    from mxbiflow.utils.logger import setup_logging

    setup_logging()
    logger.info("hello")

``from loguru import logger`` is the very same instance that
``setup_logging()`` configures (loguru's logger is a global singleton),
so no logger is returned. This requires the optional ``log`` extra.
"""

import logging
import sys
from pathlib import Path

#: The logger used across mxbiflow. A :class:`logging.NullHandler` is
#: attached so importing the library never emits "no handler" warnings;
#: the host application remains free to add its own handlers.
logger = logging.getLogger("mxbiflow")
logger.addHandler(logging.NullHandler())


class InterceptHandler(logging.Handler):
    """Bridge stdlib ``logging`` records into loguru (internal).

    Attached to the root logger by :func:`setup_logging`. Also exported
    for advanced users who want to wire the bridge into their own
    logging hierarchy, e.g.::

        logging.getLogger().addHandler(InterceptHandler())
    """

    def emit(self, record: logging.LogRecord) -> None:
        # Imported lazily so the library itself never requires loguru.
        from loguru import logger as loguru_logger

        # Get the corresponding loguru level if it exists.
        try:
            level: str | int = loguru_logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find the caller frame where the logged message originated.
        frame = logging.currentframe()
        depth = 2
        while frame is not None and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        loguru_logger.opt(depth=depth, exception=record.exc_info).log(
            level,
            record.getMessage(),
        )


def setup_logging(
    *,
    level: str | int = "DEBUG",
    log_file: str | Path | None = None,
    rotation: str = "10 MB",
    retention: str = "7 days",
    compression: str = "zip",
    serialize: bool = True,
) -> None:
    """Configure loguru as mxbiflow's log sink (batteries-included setup).

    This is a convenience for host applications that want loguru's
    formatting, rotation and JSON serialization out of the box. It:

    - attaches an :class:`InterceptHandler` to the root stdlib logger so
      mxbiflow's records are re-emitted through loguru;
    - resets loguru's global configuration and adds a stderr sink;
    - optionally adds a rotating file sink (``log_file``), mirroring the
      behaviour of the former ``init_logger()``.

    After calling this, ``from loguru import logger`` gives you the
    configured logger — loguru's logger is a global singleton, so no
    instance is returned here.

    Requires the optional ``log`` extra: ``pip install mxbiflow[log]``.
    """
    try:
        from loguru import logger as loguru_logger
    except ImportError as exc:
        raise ImportError(
            "setup_logging() requires the optional 'log' extra: "
            "pip install mxbiflow[log]"
        ) from exc

    root = logging.getLogger()
    if not any(isinstance(handler, InterceptHandler) for handler in root.handlers):
        root.addHandler(InterceptHandler())

    # Without this, the stdlib logger would inherit the root level
    # (WARNING by default) and drop DEBUG/INFO records before they can
    # reach the intercept handler.
    logger.setLevel(level)

    loguru_logger.remove()
    loguru_logger.add(sys.stderr, level=level)

    if log_file is not None:
        loguru_logger.add(
            str(log_file),
            rotation=rotation,
            retention=retention,
            compression=compression,
            encoding="utf-8",
            level=level,
            serialize=serialize,
        )


__all__ = ["InterceptHandler", "logger", "setup_logging"]
