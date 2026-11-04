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
            with patch("mxbiflow.core.path.Path.home", return_value=Path(home)):
                self.assertEqual(
                    get_database_path(),
                    Path(home) / ".config" / "mxbi" / "db.json",
                )

    def test_missing_database_loads_empty_and_is_not_created(self) -> None:
        with (
            tempfile.TemporaryDirectory() as home,
            patch("mxbiflow.core.path.Path.home", return_value=Path(home)),
        ):
            path = get_database_path()
            database = ConfigStore(path, MXBIDatabase).value

            self.assertEqual(database, MXBIDatabase())
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
