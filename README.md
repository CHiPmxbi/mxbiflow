# mxbiflow

A framework for building multi-animal, multi-stage behavioral neuroscience experiments with touchscreen interfaces.

## Overview

mxbiflow provides the core infrastructure for cognitive and behavioral experiment scheduling. It handles the experiment lifecycle — from configuration wizards and session management to real-time scene rendering and data logging — so you can focus on designing your experiment logic.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                       mxbiflow                          │
│                                                         │
│  Dialog Flow (PySide6)     Game Loop (pygame-ce)        │
│  ┌────────────────┐         ┌───────────────────┐       │
│  │ MXBIPanel      │         │ SceneManager      │       │
│  │ ExperimentPanel│ ──────▶ │   ├─ Scene A      │       │
│  └────────────────┘         │   ├─ Scene B      │       │
│                             │   └─ ...          │       │
│                             │                   │       │
│                             │ Scheduler         │       │
│                             │ DetectorBridge    │       │
│                             └───────────────────┘       │
│                                                         │
│  ConfigStore ◄──── JSON config files                    │
│  DataLogger  ────► session data output                  │
│                                                         │
│  Driver Layer                                           │
│  ┌───────────────────────────────────────────────────┐  │
│  │ RFID / Rewarder / Detector / Audio / Peripherals │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Usage

Implement your experiment as a set of scenes, register them, and launch:

```python
from pathlib import Path

from mxbiflow import SceneManager, init_gameloop, set_base_path
from mxbiflow.ui import run_wizard

set_base_path(Path.cwd())

scene_manager = SceneManager()
scene_manager.register([IDLE, Detect, Discriminate])

if not run_wizard(scene_manager):
    raise SystemExit(0)

game = init_gameloop(scene_manager, max_fps=120)
game.play()
```

Each scene implements `SceneProtocol`:

```python
class MyScene:
    _running: bool
    level_table: dict[str, list[int]] = {"default": [1, 2, 3]}

    def start(self) -> None: ...
    def quit(self) -> None: ...
    @property
    def running(self) -> bool: ...
    def handle_event(self, event: Event) -> None: ...
    def update(self, dt_s: float) -> None: ...
    def draw(self, screen: Surface) -> None: ...
```

## Logging

mxbiflow never configures logging on import. For a batteries-included
setup, enable the optional `log` extra and call `setup_logging()` once,
then use loguru directly:

```shell
uv add mxbiflow[log]
```

```python
from loguru import logger
from mxbiflow.utils.logger import setup_logging

setup_logging(level="DEBUG", log_file="log/mxbi.log")

logger.info("session started: {}", session_id)
```

`setup_logging()` wires mxbiflow's records into loguru and configures its
sinks (stderr, plus an optional rotating, JSON-serialized file log).
Because loguru's logger is a global singleton, the `logger` you import
above is the configured one — no instance is returned. The CLI
(`python -m mxbiflow`) enables this setup automatically.

Without loguru, the library stays silent: you can handle mxbiflow's
records with your own standard-library handlers instead.

## Installation

```shell
uv add mxbiflow
```

Hardware interfaces and drivers are available under `mxbiflow.driver`:

```python
from mxbiflow.driver import MXBI, MXBIModel
from mxbiflow.driver.detector import DetectorEvent
```

The former `pymxbi` package is now part of mxbiflow. Replace imports such as
`pymxbi.detector` with `mxbiflow.driver.detector`; no compatibility namespace
is installed.

## Requirements

- Python 3.14+
- pygame-ce and PySide6
