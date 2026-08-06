import unittest

import pygame

from mxbiflow.driver.detector.mock_detector import MockDetector
from mxbiflow.gameloop.detector_bridge import DetectorBridge
from mxbiflow.gameloop.shortcuts import ShortcutRegistry, register_default_shortcuts


class ShortcutRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ShortcutRegistry()

    @staticmethod
    def _keydown(key: int) -> pygame.event.Event:
        return pygame.event.Event(pygame.KEYDOWN, key=key)

    def test_registered_key_dispatches_handler(self) -> None:
        handled: list[pygame.event.Event] = []
        self.registry.register(pygame.K_ESCAPE, "Quit the game", handled.append)
        event = self._keydown(pygame.K_ESCAPE)

        self.registry.handle_event(event)

        self.assertEqual(handled, [event])

    def test_unknown_key_is_ignored(self) -> None:
        handled: list[pygame.event.Event] = []
        self.registry.register(pygame.K_ESCAPE, "Quit the game", handled.append)

        self.registry.handle_event(self._keydown(pygame.K_a))

        self.assertEqual(handled, [])

    def test_non_keydown_events_are_ignored(self) -> None:
        handled: list[pygame.event.Event] = []
        self.registry.register(pygame.K_ESCAPE, "Quit the game", handled.append)
        event = pygame.event.Event(pygame.KEYUP, key=pygame.K_ESCAPE)

        self.registry.handle_event(event)

        self.assertEqual(handled, [])

    def test_duplicate_key_raises_value_error(self) -> None:
        self.registry.register(pygame.K_ESCAPE, "Quit the game", lambda _event: None)

        with self.assertRaises(ValueError):
            self.registry.register(
                pygame.K_ESCAPE, "Quit the game again", lambda _event: None
            )


class RegisterDefaultShortcutsTests(unittest.TestCase):
    def test_builtin_shortcuts_dispatch_to_handlers(self) -> None:
        registry = ShortcutRegistry()
        quits: list[bool] = []
        captures: list[bool] = []
        detector = MockDetector()
        bridge = DetectorBridge(detector, {"rfid-a": "animal-a", "rfid-b": "animal-b"})

        register_default_shortcuts(
            registry,
            on_quit=lambda: quits.append(True),
            on_capture=lambda: captures.append(True),
            detector_bridge=bridge,
        )

        registry.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        registry.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_q))
        registry.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_c))
        registry.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_0))
        self.assertEqual(detector.current_animal, "rfid-a")
        registry.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1))
        self.assertEqual(detector.current_animal, "rfid-b")
        registry.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_l))

        self.assertEqual(quits, [True, True])
        self.assertEqual(captures, [True])
        self.assertIsNone(detector.current_animal)

    def test_default_bindings_are_exposed(self) -> None:
        registry = ShortcutRegistry()
        register_default_shortcuts(
            registry,
            on_quit=lambda: None,
            on_capture=lambda: None,
            detector_bridge=DetectorBridge(MockDetector(), {}),
        )

        expected_keys = {
            pygame.K_ESCAPE,
            pygame.K_q,
            pygame.K_c,
            *range(pygame.K_0, pygame.K_0 + 6),
            pygame.K_l,
        }
        self.assertEqual(set(registry.bindings), expected_keys)


class DetectorBridgeManualEmitTests(unittest.TestCase):
    def test_manual_emit_by_index_resolves_animal_map_order(self) -> None:
        detector = MockDetector()
        bridge = DetectorBridge(detector, {"rfid-a": "animal-a", "rfid-b": "animal-b"})

        bridge.manual_emit_by_index(0)
        self.assertEqual(detector.current_animal, "rfid-a")

        bridge.manual_emit_by_index(1)
        self.assertEqual(detector.current_animal, "rfid-b")

    def test_manual_emit_by_index_out_of_range_is_noop(self) -> None:
        detector = MockDetector()
        bridge = DetectorBridge(detector, {"rfid-a": "animal-a"})

        bridge.manual_emit_by_index(5)

        self.assertIsNone(detector.current_animal)


if __name__ == "__main__":
    unittest.main()
