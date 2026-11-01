import os

# Keep stdout clean for command output such as `mxbiflow schema`.
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from .bootstrap import init_gameloop
from .commands import CommandRegistry, NoParams, RemoteCommand, Reply
from .core.context import MXBIFlow, get_mxbiflow
from .core.path import get_base_path, set_base_path
from .scene import Scene, SceneManager

__all__ = [
    "CommandRegistry",
    "MXBIFlow",
    "NoParams",
    "RemoteCommand",
    "Reply",
    "Scene",
    "SceneManager",
    "get_base_path",
    "get_mxbiflow",
    "init_gameloop",
    "set_base_path",
]
