import unittest
from unittest.mock import Mock, patch

from mxbiflow.driver.detector.detector import DetectionResult, DetectorEvent
from mxbiflow.gameloop.detector_bridge import DetectorBridge


class DetectorBridgeTests(unittest.TestCase):
    def test_subscribes_before_begin_and_maps_identification(self) -> None:
        detector = Mock()
        callbacks = {}
        detector.register_event.side_effect = lambda event, callback: callbacks.update(
            {event: callback}
        )
        detector.begin.side_effect = lambda: callbacks[DetectorEvent.ANIMAL_IDENTIFIED](
            DetectionResult(animal_id="tag-A")
        )
        bridge = DetectorBridge(detector, {"tag-A": "animal-A"})
        bridge.start()
        with patch("mxbiflow.gameloop.detector_bridge.event.post") as post:
            bridge.emit_pygame_event()
            messages = [call.args[0].msg for call in post.call_args_list]
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].kind, DetectorEvent.ANIMAL_IDENTIFIED)
        self.assertEqual(messages[0].animal, "animal-A")

    def test_unmapped_identification_does_not_switch_task(self) -> None:
        detector = Mock()
        callbacks = {}
        detector.register_event.side_effect = lambda event, callback: callbacks.update(
            {event: callback}
        )
        bridge = DetectorBridge(detector, {})
        bridge.start()
        with self.assertLogs("mxbiflow.rfid", level="WARNING"):
            callbacks[DetectorEvent.ANIMAL_IDENTIFIED](
                DetectionResult(animal_id="missing")
            )
        with patch("mxbiflow.gameloop.detector_bridge.event.post") as post:
            bridge.emit_pygame_event()
        post.assert_not_called()
