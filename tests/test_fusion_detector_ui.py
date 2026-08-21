# pyright: reportPrivateUsage=false

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGridLayout

from mxbiflow.driver.detector import FusionContinuousDetectorModel
from mxbiflow.ui.components.device_card.detector.fusion_detector import (
    FusionDetectorCard,
)


class FusionDetectorCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_filter_configuration_round_trip(self) -> None:
        card = FusionDetectorCard()
        model = FusionContinuousDetectorModel(
            beam_break_filter_enabled=True,
            beam_break_filter_duration=0.35,
        )

        card.load_config(model)

        self.assertTrue(card._checkbox_leave_filter.isChecked())
        self.assertTrue(card._spin_leave_filter_duration.isEnabled())
        self.assertAlmostEqual(card.result.beam_break_filter_duration, 0.35)
        self.assertTrue(card.result.beam_break_filter_enabled)

        card._checkbox_leave_filter.setChecked(False)

        self.assertFalse(card._spin_leave_filter_duration.isEnabled())
        self.assertFalse(card.result.beam_break_filter_enabled)

    @patch(
        "mxbiflow.ui.components.device_card.detector.fusion_detector.get_all_ports",
        return_value=["/dev/ttyUSB9"],
    )
    def test_full_configuration_round_trip(self, _get_all_ports: object) -> None:
        card = FusionDetectorCard()
        model = FusionContinuousDetectorModel(
            enabled=True,
            id=7,
            pin=13,
            port="/dev/ttyUSB9",
            baudrate=115200,
            poll_interval=0.2,
            rfid_timeout=0.08,
            beam_break_filter_enabled=True,
            beam_break_filter_duration=0.35,
        )

        card.load_config(model)

        self.assertEqual(card.result, model)

    def test_related_fields_are_grouped_into_four_rows(self) -> None:
        card = FusionDetectorCard()

        self.assertEqual(card.layout_config.rowCount(), 1)
        self.assertEqual(card._compact_layout.rowCount(), 4)
        self.assertGreaterEqual(card.minimumWidth(), 400)
        self.assertIsInstance(card._compact_layout, QGridLayout)

    def test_enabled_checkbox_can_be_clicked(self) -> None:
        card = FusionDetectorCard()
        card.show()
        self.app.processEvents()

        self.assertFalse(card.checkbox_enabled.isChecked())
        QTest.mouseClick(card.checkbox_enabled, Qt.MouseButton.LeftButton)

        self.assertTrue(card.checkbox_enabled.isChecked())


if __name__ == "__main__":
    unittest.main()
