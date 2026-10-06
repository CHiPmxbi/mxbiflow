# pyright: reportPrivateUsage=false

import unittest
from unittest.mock import Mock, patch

from serial import SerialException

from mxbiflow.driver.peripheral.rfid.dorset_lid665v42 import (
    DorsetLID665v42,
    Result,
    _LID665v42FrameParser,
)


class RFIDLoggingTests(unittest.TestCase):
    def test_all_parsed_tags_are_logged_even_when_latest_slot_is_overwritten(
        self,
    ) -> None:
        serial = Mock()
        serial.port = "test-port"
        serial.read.side_effect = [b"x", b"y", SerialException("disconnected")]
        with patch(
            "mxbiflow.driver.peripheral.rfid.dorset_lid665v42.Serial",
            return_value=serial,
        ):
            reader = DorsetLID665v42("test-port", 57600)
        frames = [Result(100.0, "A"), Result(101.0, "B")]
        with (
            patch.object(reader._parser, "feed", side_effect=frames),
            self.assertLogs("mxbiflow.rfid", level="INFO") as captured,
        ):
            reader._read_loop()
        tags = [
            record
            for record in captured.records
            if record.getMessage() == "RFID tag parsed"
        ]
        self.assertEqual([record.__dict__["animal_id"] for record in tags], ["A", "B"])
        self.assertEqual(
            [record.__dict__["detect_time"] for record in tags], [100.0, 101.0]
        )
        self.assertTrue(
            all(record.__dict__["port"] == "test-port" for record in captured.records)
        )
        self.assertIn("disconnected", captured.records[-1].getMessage())
        self.assertEqual(reader.read(), frames[-1])
        self.assertIsNone(reader.read())

    def test_repeated_parser_errors_are_logged_each_time(self) -> None:
        parser = _LID665v42FrameParser("test-port")
        with self.assertLogs("mxbiflow.rfid", level="WARNING") as captured:
            parser.feed(b"x")
            parser.feed(b"x")
            parser._build_result()
        self.assertEqual(len(captured.records), 3)
        self.assertIn(
            "shorter than protocol minimum", captured.records[-1].getMessage()
        )

    def test_serial_initialization_failure_is_logged_and_raised(self) -> None:
        with (
            patch(
                "mxbiflow.driver.peripheral.rfid.dorset_lid665v42.Serial",
                side_effect=SerialException("unavailable"),
            ),
            self.assertLogs("mxbiflow.rfid", level="ERROR") as captured,
            self.assertRaises(SerialException),
        ):
            DorsetLID665v42("test-port", 57600)
        self.assertEqual(captured.records[0].__dict__["port"], "test-port")
