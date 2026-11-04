import logging
import os
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger("mxbiflow")


class ConfigStore[T: BaseModel]:
    def __init__(
        self,
        config_path: Path,
        config_class: type[T],
        *,
        create_default: bool = True,
    ) -> None:
        self._config_path = config_path
        self._config_class = config_class
        self._create_default = create_default
        self._config = self._load_config()

    @property
    def value(self) -> T:
        return self._config

    def _ensure_config_readable(self) -> None:
        if not self._config_path.exists():
            raise FileNotFoundError(f"Config file {self._config_path} not found")

        if not os.access(self._config_path, os.R_OK):
            raise PermissionError(f"Config file {self._config_path} is not readable")

    def _load_config(self) -> T:
        try:
            self._ensure_config_readable()
            text = self._config_path.read_text(encoding="utf-8")
            return self._config_class.model_validate_json(text)
        except Exception as e:
            if self._create_default:
                # Only save() writes: loading never changes the file.
                if self._config_path.exists():
                    logger.warning(
                        "using defaults: %s is invalid: %s", self._config_path, e
                    )
                return self._config_class()
            raise RuntimeError(
                f"Failed to load config file {self._config_path}: {e}"
            ) from e

    def save(self, data: T | None = None) -> None:
        if data is not None:
            self._config = data

        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._config_path.write_text(
                self._config.model_dump_json(indent=4),
                encoding="utf-8",
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to save config file {self._config_path}: {e}"
            ) from e
