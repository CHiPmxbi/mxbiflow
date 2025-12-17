import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from mxbi.path import DATA_DIR_PATH
from mxbi.utils.logger import logger

if TYPE_CHECKING:
    from mxbi.models.session import SessionState

_now = datetime.now()


class DataLogger:
    def __init__(
        self, session_config: "SessionState", monkey: str, filename: str
    ) -> None:
        self.__session_state = session_config
        self._monkey = monkey
        self._filename = filename
        self._session_id = self.__session_state.session_id

        self._data_dir = self._ensure_data_dir()

    @staticmethod
    def init_session_id() -> int:
        now = datetime.now()
        date_path = Path(f"{now.year}{now.month:02d}{now.day:02d}")
        base_path = DATA_DIR_PATH / date_path

        if not base_path.exists():
            return 0

        latest_session_id = max(
            (
                int(child.name)
                for child in base_path.iterdir()
                if child.is_dir() and child.name.isdigit()
            ),
            default=-1,
        )

        return latest_session_id + 1

    def _ensure_data_dir(self) -> Path:
        date_path = Path(f"{_now.year}{_now.month:02d}{_now.day:02d}")
        session_path = Path(f"{self._session_id}")
        monkey_path = Path(f"{self._monkey}")

        base_dir = DATA_DIR_PATH / date_path / session_path / monkey_path

        try:
            base_dir.mkdir(parents=True, exist_ok=True)
            return base_dir
        except Exception as e:
            logger.error(f"Failed to create data directory: {e}")
            sys.exit(1)

    def _get_path(self, suffix: str) -> Path:
        return self._data_dir / f"{self._filename}{suffix}"

    def save_jsonl(self, data: dict) -> None:
        jsonl_path = self._get_path(".jsonl")
        try:
            json_line = json.dumps(data, ensure_ascii=False)

            with open(jsonl_path, "a", encoding="utf-8") as f:
                f.write(json_line + "\n")

        except TypeError as e:
            logger.error(f"Data is not JSON serializable: {e}")
            raise
        except IOError as e:
            logger.error(f"Failed to write to file {jsonl_path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error while writing data: {e}")
            raise

    def save_json(self, data: dict) -> None:
        json_path = self._get_path(".json")
        try:
            json_path.parent.mkdir(parents=True, exist_ok=True)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except TypeError as e:
            logger.error(f"Data is not JSON serializable: {e}")
            raise
        except IOError as e:
            logger.error(f"Failed to write to file {json_path}: {e}")
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


if __name__ == "__main__":
    data = {"key": "value"}
    from datetime import datetime

    from mxbi.config import session_config
    from mxbi.models.session import SessionState

    state = SessionState(
        session_id=0,
        session_config=session_config.value,
        start_time=datetime.now().timestamp(),
        end_time=datetime.now().timestamp(),
    )

    recorder = DataLogger(state, "mock", "mock")

    for i in range(10):
        recorder.save_jsonl(data)
