import json
import os
from pathlib import Path
from typing import Generic, TypeVar

from pydantic import BaseModel, ValidationError

from mxbi.utils.logger import logger

T = TypeVar("T", bound=BaseModel)


class Configure(Generic[T]):
    def __init__(self, config_path: Path, config_class: type[T]) -> None:
        self._config_path = config_path
        self._config_class = config_class
        self._config = self._load_config()

    @property
    def value(self) -> T:
        return self._config

    def _create_default_config(self) -> T:
        config = self._config_class()
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)

            with self._config_path.open("w", encoding="utf-8") as f:
                json.dump(config.model_dump(), f, indent=4)

            logger.info(f"Created default configuration file at {self._config_path}")
            return config
        except OSError as e:
            logger.error(
                f"Failed to create default configuration file at {self._config_path}: {str(e)}"
            )
            raise

    def _load_config(self) -> T:
        try:
            if not self._config_path.exists():
                logger.warning(f"Configuration file not found at {self._config_path}")
                return self._create_default_config()

            if not os.access(self._config_path, os.R_OK):
                logger.warning(
                    f"No read permission for configuration file at {self._config_path}"
                )
                return self._create_default_config()

            with self._config_path.open("r", encoding="utf-8") as f:
                logger.info(f"Loading configuration file from {self._config_path}")
                return self._config_class.model_validate_json(f.read())

        except (ValidationError, ValueError) as e:
            logger.error(f"Invalid configuration format: {e}")
            return self._create_default_config()
        except Exception as e:
            logger.error(f"Unexpected error while loading configuration: {e}")
            return self._create_default_config()

    def save(self, data: T | None = None) -> None:
        try:
            if data is not None:
                self._config = data

            self._config_path.parent.mkdir(parents=True, exist_ok=True)

            with self._config_path.open("w", encoding="utf-8") as f:
                json.dump(self._config.model_dump(), f, indent=4)

            logger.info(f"Configuration saved to {self._config_path}")
        except Exception as e:
            logger.error(f"Failed to save configuration file: {e}")
            raise
