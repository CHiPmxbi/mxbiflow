import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mxbiflow.core.config_store import ConfigStore
from mxbiflow.core.path import get_database_path, set_base_path
from mxbiflow.models.database import MXBIDatabase


class DatabaseTests(unittest.TestCase):
    def test_database_path_uses_home_instead_of_base_path(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            set_base_path("/unrelated/project")
            with patch.dict(os.environ, {"HOME": home}):
                self.assertEqual(
                    get_database_path(),
                    Path(home) / ".config" / "mxbi" / "db.json",
                )

    def test_missing_database_is_created_with_empty_data(self) -> None:
        with (
            tempfile.TemporaryDirectory() as home,
            patch.dict(os.environ, {"HOME": home}),
        ):
            path = get_database_path()
            database = ConfigStore(path, MXBIDatabase).value

            self.assertEqual(database, MXBIDatabase())
            self.assertTrue(path.is_file())
            self.assertEqual(
                MXBIDatabase.model_validate_json(path.read_text(encoding="utf-8")),
                database,
            )

    def test_database_path_requires_home(self) -> None:
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(KeyError):
            get_database_path()


if __name__ == "__main__":
    unittest.main()
