# pymxbi

Python interfaces and drivers for mxbi

English | [中文](README.zh.md)

## Install

```bash
pip install pymxbi
```

Or with `uv`:

```bash
uv add pymxbi
```

## Public API

### Detectors

- `pymxbi.detector.detector.Detector`: base class + event registration
- `pymxbi.detector.detector.DetectorEvent` / `DetectorState` / `DetectionResult`
- `pymxbi.detector.beam_break_rfid_detector.BeamBreakRFIDDetector`: beam-break + RFID combined detector

### Rewarders

- `pymxbi.rewarder.rewarder.Rewarder`: reward backend protocol (`open`, `give_reward*`, `stop_reward`, `close`)
- `pymxbi.rewarder.pump_rewarder.PumpRewarder`: time-based reward delivery via a pump
- `pymxbi.rewarder.mock_rewarder.MockRewarder`: logging-only mock implementation

### Peripherals

- Pumps: `pymxbi.peripheral.pumps.pump.Pump` / `Direction`, `pymxbi.peripheral.pumps.RPI_gpio_pump.RPIGpioPump`
- Through-beam sensors: `pymxbi.peripheral.through_beam_sensor.through_beam_sensor.ThroughBeamSensor`, `pymxbi.peripheral.through_beam_sensor.RPI_IR_break_beam_sensor.RPIIRBreakBeamSensor`
- RFID reader: `pymxbi.peripheral.rfid.dorset_lid665v42.DorsetLID665v42` (`open`, `begin`, `read`, `close`, `errno`)

### Utilities

- Audio volume: `pymxbi.peripheral.amixer.amixer.set_master_volume`, `set_digital_volume` (calls `amixer`)

## Notes

- Typed package (`py.typed`), requires Python `>=3.14`.
