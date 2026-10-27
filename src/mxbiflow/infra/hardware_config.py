"""The rig hardware configuration, shared by every experiment on the device (#210).

cogmote keeps named hardware presets per device and sends the current one
under the ``hardware`` key of the device configuration that cogmoteGO caches
(cagelab/cogmote#439). At each start it is copied to the device-global file
(:func:`~mxbiflow.core.path.get_mxbi_config_path`), which the wizard's MXBI
panel also edits; the file is used as is when cogmote has no preset or
cogmoteGO is unreachable.
"""

import shutil
import socket

from pydantic import ValidationError
from pymotego import Client

from ..core.path import get_legacy_mxbi_config_path, get_mxbi_config_path
from ..driver import MXBIModel
from ..utils.logger import logger
from .cogmote_config import CogmoteConfigError


class HardwareConfigError(CogmoteConfigError):
    """No usable hardware configuration; the message says why."""


def sync_hardware_config(client: Client | None = None) -> None:
    """Update the device-global hardware configuration before a run.

    An experiment's own ``config/mxbi.json`` is moved there once, when the
    device has none yet; then cogmote's current preset replaces it.
    Raises :class:`HardwareConfigError` for a preset mxbiflow cannot read.
    """
    path = get_mxbi_config_path()
    legacy = get_legacy_mxbi_config_path()
    if not path.exists() and legacy.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(legacy, path)
        logger.info("hardware configuration moved from %s to %s", legacy, path)

    try:
        hardware = (
            (client if client is not None else Client()).get_config().get("hardware")
        )
    except Exception as error:  # noqa: BLE001 - the local copy still runs
        logger.warning("cogmote hardware configuration not read: %s", error)
        return
    if hardware is None:
        return
    try:
        config = MXBIModel.model_validate(hardware)
    except ValidationError as error:
        raise HardwareConfigError(
            f"the hardware preset in cogmote is invalid: {error}"
        ) from error
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(config.model_dump_json(indent=4), encoding="utf-8")


def read_hardware_config() -> MXBIModel:
    """Return the device-global hardware configuration.

    Raises :class:`HardwareConfigError` when there is none or it is invalid.
    """
    path = get_mxbi_config_path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise HardwareConfigError(
            "no hardware configuration: choose a hardware preset for this device "
            "in cogmote, or configure the rig in the MXBI panel"
        ) from error
    try:
        return MXBIModel.model_validate_json(text)
    except ValidationError as error:
        raise HardwareConfigError(
            f"the hardware configuration {path} is invalid: {error}"
        ) from error


def device_name(client: Client | None = None) -> str:
    """Return the device name in cogmote, or the host name without one."""
    try:
        device = (client if client is not None else Client()).get_config().get("device")
        if isinstance(device, dict) and isinstance(name := device.get("name"), str):
            return name
    except Exception as error:  # noqa: BLE001 - reports still need a title
        logger.warning("cogmote device name not read: %s", error)
    return socket.gethostname()
