# pymxbi

为 mxbi 硬件设备提供面向 Python 的接口与驱动

中文 | [English](README.md)

## 安装

```bash
pip install pymxbi
```

或使用 `uv`：

```bash
uv add pymxbi
```

## 对外接口

### 检测器（Detectors）

- `pymxbi.detector.detector.Detector`：检测器基类 + 事件注册
- `pymxbi.detector.detector.DetectorEvent` / `DetectorState` / `DetectionResult`
- `pymxbi.detector.beam_break_rfid_detector.BeamBreakRFIDDetector`：红外对射断光 + RFID 联合检测

### 奖励器（Rewarders）

- `pymxbi.rewarder.rewarder.Rewarder`：奖励后端协议（`open`, `give_reward*`, `stop_reward`, `close`）
- `pymxbi.rewarder.pump_rewarder.PumpRewarder`：基于泵的时间型奖励发放
- `pymxbi.rewarder.mock_rewarder.MockRewarder`：仅记录日志的 mock 实现

### 外设（Peripherals）

- 泵：`pymxbi.peripheral.pumps.pump.Pump` / `Direction`，`pymxbi.peripheral.pumps.RPI_gpio_pump.RPIGpioPump`
- 断光传感器：`pymxbi.peripheral.through_beam_sensor.through_beam_sensor.ThroughBeamSensor`，`pymxbi.peripheral.through_beam_sensor.RPI_IR_break_beam_sensor.RPIIRBreakBeamSensor`
- RFID 读卡器：`pymxbi.peripheral.rfid.dorset_lid665v42.DorsetLID665v42`（`open`, `begin`, `read`, `close`, `errno`）

### 工具

- 音量控制：`pymxbi.peripheral.amixer.amixer.set_master_volume`、`set_digital_volume`（内部调用 `amixer`）

## 说明

- 包含类型信息（`py.typed`），要求 Python `>=3.14`。
