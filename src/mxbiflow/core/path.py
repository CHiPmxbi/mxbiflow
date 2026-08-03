import os
from pathlib import Path

_base_path: Path | None = None

CONFIG_SESSION_FILENAME = "session.json"
DATABASE_FILENAME = "db.json"
MXBI_CONFIG_FILENAME = "mxbi.json"
MXBI_PANEL_CONFIG_FILENAME = "mxbi_panel.json"
CROSS_MODAL_CONFIG_FILENAME = "config_cross_modal.json"


def set_base_path(path: Path | str) -> None:
    global _base_path
    _base_path = Path(path)


def get_base_path() -> Path:
    if _base_path is None:
        raise RuntimeError("Base path not set. Call set_base_path() first.")
    return _base_path


def get_config_dir_path() -> Path:
    return get_base_path() / "config"


def get_mxbi_config_path() -> Path:
    return get_config_dir_path() / MXBI_CONFIG_FILENAME


def get_mxbi_panel_config_path() -> Path:
    return get_config_dir_path() / MXBI_PANEL_CONFIG_FILENAME


def get_config_session_path() -> Path:
    return get_config_dir_path() / CONFIG_SESSION_FILENAME


def get_database_path() -> Path:
    return Path(os.environ["HOME"]) / ".config" / "mxbi" / DATABASE_FILENAME


def get_cross_modal_config_path() -> Path:
    return get_config_dir_path() / CROSS_MODAL_CONFIG_FILENAME


def get_data_dir_path() -> Path:
    return get_base_path() / "data"


def get_log_path() -> Path:
    return get_base_path() / "log"


def get_samba_mount_path() -> Path:
    return get_base_path() / "samba_mount"


def get_internal_state_path() -> Path:
    return get_base_path() / ".mxbiflow" / "state"


def get_runtime_state_path() -> Path:
    return get_internal_state_path() / "runtime.json"
