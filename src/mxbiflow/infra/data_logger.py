import csv
import json
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path

from ..models.session import Session
from ..utils.logger import logger

type LogRecord = Mapping[str, object]


class DataLoggerType(StrEnum):
    JSONL = "jsonl"
    JSON = "json"
    CSV = "csv"


class DataLogger:
    def __init__(
        self,
        session: Session,
        *,
        animal: str,
        stage: str,
        filename: str = "result",
        type: DataLoggerType = DataLoggerType.JSONL,
    ) -> None:
        if session.data_root is None:
            raise RuntimeError(
                "Session data path is not set. Call Session.start() first."
            )

        self._session_path = session.absolute_animal_data_path(animal)
        self._session = session
        self._animal = animal
        self._stage = stage
        self._filename = filename
        self._type = type

        self._data_dir = self._ensure_data_dir()
        self._data_path = self._get_path(f".{self._type.value}")

    @property
    def path(self) -> Path:
        return self._data_path

    def _ensure_data_dir(self) -> Path:
        base_dir = self._session_path / self._stage

        try:
            already_exists = base_dir.exists()
            base_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            logger.exception("Failed to create data directory: %s", base_dir)
            raise

        logger.info(
            "Data directory %s: %s",
            "exists" if already_exists else "created",
            base_dir,
        )

        return base_dir

    def _get_path(self, suffix: str) -> Path:
        return self._data_dir / f"{self._filename}{suffix}"

    def _register_data_path(self) -> None:
        self._session.register_stage_data_path(
            animal=self._animal,
            stage=self._stage,
        )

    def save(self, data: LogRecord) -> None:
        match self._type:
            case DataLoggerType.JSONL:
                self._save_jsonl(data)
            case DataLoggerType.JSON:
                self._save_json(data)
            case DataLoggerType.CSV:
                self.save_csv_row(data)

    def _save_jsonl(self, data: LogRecord) -> None:
        try:
            json_line = json.dumps(data, ensure_ascii=False)

            with open(self._data_path, "a", encoding="utf-8") as f:
                f.write(json_line + "\n")

        except TypeError as e:
            logger.error("Data is not JSON serializable: %s", e)
            raise
        except OSError as e:
            logger.error("Failed to write to file %s: %s", self._data_path, e)
            raise
        except Exception as e:
            logger.error("Unexpected error while writing data: %s", e)
            raise

        self._register_data_path()

    def _save_json(self, data: LogRecord) -> None:
        try:
            self._data_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._data_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except TypeError as e:
            logger.error("Data is not JSON serializable: %s", e)
            raise
        except OSError as e:
            logger.error("Failed to write to file %s: %s", self._data_path, e)
            raise
        except Exception as e:
            logger.error("Unexpected error while writing JSON data: %s", e)
            raise

        self._register_data_path()

    def save_csv_row(self, data: LogRecord) -> None:
        csv_path = self._get_path(".csv")
        try:
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            file_exists = csv_path.exists() and csv_path.stat().st_size > 0

            fieldnames: list[str] = sorted(data)

            with csv_path.open("a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()
                writer.writerow({k: data.get(k, "") for k in fieldnames})
        except Exception as e:
            logger.error("Failed to write CSV row to %s: %s", csv_path, e)
            raise

        self._register_data_path()
