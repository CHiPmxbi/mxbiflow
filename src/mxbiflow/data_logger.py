import csv
import json
import sys
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from .utils.logger import logger


now = datetime.now()


class DataLoggerType(StrEnum):
    JSONL = "jsonl"
    JSON = "json"
    CSV = "csv"


class DataLogger:
    def __init__(
        self,
        path: Path,
        session_id: int,
        monkey: str,
        filename: str,
        type: DataLoggerType = DataLoggerType.JSONL,
    ) -> None:
        self._path = path
        self._session_id = session_id
        self._monkey = monkey
        self._filename = filename
        self._type = type

        self._data_dir = self._ensure_data_dir()
        self._data_path = self._get_path(f".{self._type.value}")

    @property
    def path(self) -> Path:
        return self._data_path

    def _ensure_data_dir(self) -> Path:
        date_path = Path(f"{now.year}{now.month:02d}{now.day:02d}")
        session_path = Path(f"{self._session_id}")
        monkey_path = Path(f"{self._monkey}")

        base_dir = self._path / date_path / session_path / monkey_path

        try:
            base_dir.mkdir(parents=True, exist_ok=True)
            return base_dir
        except Exception as e:
            logger.error(f"failed to create {base_dir}: {e}")
            sys.exit(1)

    def _get_path(self, suffix: str) -> Path:
        return self._data_dir / f"{self._filename}{suffix}"

    def save(self, data: dict) -> None:
        match self._type:
            case DataLoggerType.JSONL:
                self._save_jsonl(data)
            case DataLoggerType.JSON:
                self._save_json(data)
            case DataLoggerType.CSV:
                self.save_csv_row(data)

    def _save_jsonl(self, data: dict) -> None:
        try:
            json_line = json.dumps(data, ensure_ascii=False)

            with open(self._data_path, "a", encoding="utf-8") as f:
                f.write(json_line + "\n")

        except TypeError as e:
            logger.error(f"Data is not JSON serializable: {e}")
            raise
        except IOError as e:
            logger.error(f"Failed to write to file {self._data_path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error while writing data: {e}")
            raise

    def _save_json(self, data: dict) -> None:
        try:
            self._data_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._data_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except TypeError as e:
            logger.error(f"Data is not JSON serializable: {e}")
            raise
        except IOError as e:
            logger.error(f"Failed to write to file {self._data_path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error while writing JSON data: {e}")
            raise

    def save_csv_row(self, data: dict) -> None:
        csv_path = self._get_path(".csv")
        try:
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            file_exists = csv_path.exists() and csv_path.stat().st_size > 0

            fieldnames = sorted(data.keys())

            with csv_path.open("a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()
                writer.writerow({k: data.get(k, "") for k in fieldnames})
        except Exception as e:
            logger.error(f"Failed to write CSV row to {csv_path}: {e}")
            raise
