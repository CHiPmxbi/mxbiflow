# mxbiflow

A framework for building multi-animal, multi-stage behavioral neuroscience experiments with touchscreen interfaces.

## Overview

mxbiflow provides the core infrastructure for cognitive and behavioral experiment scheduling. It handles the experiment lifecycle — from configuration wizards and session management to real-time scene rendering and data logging — so you can focus on designing your experiment logic.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                       mxbiflow                          │
│                                                         │
│  Wizard (PySide6)          Game Loop (pygame-ce)        │
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
└─────────────────────────────────────────────────────────┘
         │
         ▼
┌───────────────────┐
│     pymxbi        │
│  RFID / Rewarder  │
│  Detector / Audio │
└───────────────────┘
```

## Usage

Implement your experiment as a set of scenes, register them, and launch:

```python
from pathlib import Path

from mxbiflow import SceneManager, init_gameloop, set_base_path
from mxbiflow.ui.wizard import config_wizard

set_base_path(Path.cwd())

scene_manager = SceneManager()
scene_manager.register([IDLE, Detect, Discriminate])

config_wizard(scene_manager)
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

## Installation

```shell
uv add mxbiflow
```

## Requirements

- Python 3.14+
- pygame-ce, PySide6, pymxbi
