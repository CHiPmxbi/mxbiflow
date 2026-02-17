from pathlib import Path

_base_path: Path | None = None

CONFIG_SESSION_FILENAME = "session.json"
OPTIONS_SESSION_FILENAME = "options.json"
MXBI_CONFIG_FILENAME = "mxbi.json"
MXBI_PANEL_CONFIG_FILENAME = "mxbi_panel.json"
CROSS_MODAL_CONFIG_FILENAME = "config_cross_modal.json"
SAMBA_BACKUP_DIR_NAME = "backup"
SERVICE_DIR_NAME = "services"
MOUNT_SERVICE_NAME = "mount.service"
SYNC_SERVICE_NAME = "sync.service"


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


def get_options_session_path() -> Path:
    return get_config_dir_path() / OPTIONS_SESSION_FILENAME


def get_cross_modal_config_path() -> Path:
    return get_config_dir_path() / CROSS_MODAL_CONFIG_FILENAME


def get_data_dir_path() -> Path:
    return get_base_path() / "data"


def get_log_path() -> Path:
    return get_base_path() / "log"


def get_samba_mount_path() -> Path:
    return get_base_path() / "samba_mount"


def get_samba_backup_dir_path() -> Path:
    return get_samba_mount_path() / SAMBA_BACKUP_DIR_NAME


def get_service_dir_path() -> Path:
    return get_base_path() / SERVICE_DIR_NAME


def get_mount_service_path() -> Path:
    return get_service_dir_path() / MOUNT_SERVICE_NAME


def get_sync_service_path() -> Path:
    return get_service_dir_path() / SYNC_SERVICE_NAME


def get_internal_state_path() -> Path:
    return get_base_path() / ".mxbiflow" / "state"


def get_session_counter_path() -> Path:
    return get_internal_state_path() / "session_counter.json"
