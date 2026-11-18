import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

from gpiozero import Device
from gpiozero.pins.mock import MockFactory
from pydantic import ValidationError

from mxbiflow.driver import MXBIModel, build_mxbi
from mxbiflow.driver.channels import (
    DetectorInput,
    GpioInput,
    GpioOutput,
    RewarderOutput,
)

RIG: dict[str, Any] = {
    "rewarders": [{"type": "mock", "id": 0, "enabled": True}],
    "detectors": [{"type": "mock", "id": 0, "enabled": True}],
}


class GpioTestCase(unittest.TestCase):
    def setUp(self) -> None:
        previous = Device.pin_factory
        self.pins = MockFactory()
        Device.pin_factory = self.pins
        self.addCleanup(setattr, Device, "pin_factory", previous)
        self.addCleanup(self.pins.close)


class GpioChannelTests(GpioTestCase):
    def test_an_input_reports_its_edges_in_order_with_their_times(self) -> None:
        lick = GpioInput(17)
        self.addCleanup(lick.close)
        self.assertFalse(lick.level())

        self.pins.pin(17).drive_high()
        self.pins.pin(17).drive_low()
        self.pins.pin(17).drive_high()

        changes = lick.changes()
        self.assertEqual([high for _, high in changes], [True, False, True])
        self.assertEqual(sorted(at for at, _ in changes), [at for at, _ in changes])
        self.assertTrue(lick.level())
        self.assertEqual(lick.changes(), [])

    def test_a_pulled_up_input_is_high_when_its_pin_is_low(self) -> None:
        port = GpioInput(18, pull_up=True)
        self.addCleanup(port.close)
        self.assertFalse(port.level())

        self.pins.pin(18).drive_low()

        self.assertTrue(port.level())
        self.assertEqual([high for _, high in port.changes()], [True])

    def test_an_output_drives_its_pin(self) -> None:
        laser = GpioOutput(27)
        inverted = GpioOutput(22, active_high=False)
        self.addCleanup(laser.close)
        self.addCleanup(inverted.close)
        self.assertEqual((self.pins.pin(27).state, self.pins.pin(22).state), (0, 1))

        laser.set(True)
        inverted.set(True)

        self.assertEqual((self.pins.pin(27).state, self.pins.pin(22).state), (1, 0))


class DeviceChannelTests(unittest.TestCase):
    def test_a_detector_input_changes_when_the_animal_comes_and_goes(self) -> None:
        detector: Any = SimpleNamespace(current_animal=None)
        beam = DetectorInput(detector)
        self.assertEqual((beam.level(), beam.changes()), (False, []))

        detector.current_animal = "a"

        self.assertEqual([high for _, high in beam.changes()], [True])
        self.assertEqual(beam.changes(), [])

    def test_a_rewarder_output_runs_the_rewarder_while_high(self) -> None:
        rewarder = Mock()
        reward = RewarderOutput(rewarder)

        reward.set(True)
        rewarder.give_reward.assert_called_once()
        rewarder.stop_reward.assert_not_called()
        reward.set(False)

        rewarder.stop_reward.assert_called_once_with()


class WiringTests(GpioTestCase):
    def test_the_rig_configuration_wires_channels_to_devices_and_pins(self) -> None:
        config = MXBIModel.model_validate(
            RIG
            | {
                "channels": {
                    "inputs": {
                        "beam": {"type": "detector", "id": 0},
                        "lick_left": {"type": "gpio", "pin": 17, "bounce_ms": 5},
                    },
                    "outputs": {
                        "reward": {"type": "rewarder", "id": 0},
                        "laser": {"type": "gpio", "pin": 27},
                    },
                }
            }
        )

        mxbi = build_mxbi(config, Mock())
        self.addCleanup(mxbi.quit)

        self.assertIsInstance(mxbi.inputs["beam"], DetectorInput)
        self.assertIsInstance(mxbi.inputs["lick_left"], GpioInput)
        self.assertIsInstance(mxbi.outputs["reward"], RewarderOutput)
        mxbi.outputs["laser"].set(True)
        self.assertEqual(self.pins.pin(27).state, 1)

    def test_a_wire_to_a_device_the_rig_lacks_fails_with_the_channel(self) -> None:
        config = MXBIModel.model_validate(
            RIG | {"channels": {"inputs": {"beam": {"type": "detector", "id": 3}}}}
        )

        with self.assertRaisesRegex(ValueError, 'input "beam" is wired to detector 3'):
            build_mxbi(config, Mock())

    def test_a_floating_pin_needs_its_active_level(self) -> None:
        for wire in (
            {"type": "gpio", "pin": 17, "pull_up": None},
            {"type": "gpio", "pin": 17, "active_high": True},
        ):
            with self.subTest(wire=wire), self.assertRaises(ValidationError):
                MXBIModel.model_validate({"channels": {"inputs": {"lick": wire}}})
