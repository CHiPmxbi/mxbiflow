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

from mxbiflow import SceneManager, set_base_path
from mxbiflow.run import run_experiment
from mxbiflow.utils.logger import setup_logging

set_base_path(Path.cwd())
setup_logging()

scene_manager = SceneManager()
scene_manager.register([IDLE, Detect, Discriminate])

run_experiment(scene_manager, post_processors=STAGE_POST_PROCESSORS, max_fps=120)
```

`run_experiment` runs the wizard, plays the session, finishes the run (see
[Run end](#run-end)) and reports crashes. With `--from-cogmote` on the command line
(`uv run main.py --from-cogmote`, or `mxbiflow run --from-cogmote`) it starts
from the cogmote configuration instead, without any dialog. The building
blocks (`run_wizard`, `init_gameloop`, `run_session_post_processing`) stay
available for custom flows.

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
uv add "mxbiflow[log] @ git+https://github.com/CHiPmxbi/mxbiflow.git@<commit>"
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

RFID tags, errors, and identity changes also go to a separate `rfid.log`
beside the main log, with the same rotation and retention settings. Pass
`rfid_log_file="log/custom-rfid.log"` to choose its location or
`rfid_log_file=None` to disable it. With `log_file=None`, no RFID file is
created unless an explicit RFID path is supplied.

The fusion detector waits for RFID after the beam is broken (defaults:
50 ms polling, 10 s timeout). After the timeout it reports an unknown
animal and keeps scanning until identification or departure. A late
identification emits `ANIMAL_IDENTIFIED`; the scheduler applies the new
identity after the current trial ends. Existing trial data stays with
the previous animal. The first confirmed identity is fixed until departure.

Without loguru, the library stays silent: you can handle mxbiflow's
records with your own standard-library handlers instead.

## Trial status

After each trial, a scene reports the result once:

```python
get_mxbiflow().publish_trial(result.model_dump(), correct=is_correct)
```

mxbiflow patches the device status in cogmoteGO (animal, `stage@level`,
trial count and accuracy for this session) so the cogmote device page shows
the run live, and publishes the record to the `trials` broadcast. Pass
`correct=None` for trials that should not count toward accuracy. Requests
run on a background thread; when cogmoteGO is unreachable they are logged
and dropped, and the game loop carries on. The device goes back to `idle`
when the game loop quits.

## Experiment configuration in cogmote

Operators configure a run in cogmote instead of the wizard: the cage's
animals with stage and level, and the parameters. The form is generated from
the JSON Schema of `mxbiflow.models.ExperimentConfig`, which
`mxbiflow schema` prints; cogmote keeps a copy pinned to an mxbiflow commit.
cogmote fills in each animal's CogMatrix name and RFID tags and sends the
configuration to the rig with the device config.

The rig never queries CogMatrix for animals: the wizard offers the animals of
this configuration, read from cogmoteGO with `get_config()`, with their RFID
tags (`mxbiflow.infra.cogmote_config.read_experiment_config`). A tag of no
configured animal is logged and starts no task.

A headless run (`--from-cogmote`) is one session: it writes the session
configuration from cogmote and starts the game loop, as the wizard does. An
animal keeps its local stage and level from earlier runs until an operator
changes them in cogmote. A configuration that cannot start, for example a stage
the experiment does not register, is sent as a critical notification and the
process exits with status 1. Run it as a systemd user service that cogmoteGO
allows (`services` in its config), so Start and Stop in cogmote control it;
SIGTERM ends the game loop like the quit command, so a stopped run is still
ended and uploaded. Each run clears the `trials` broadcast first, so the
cogmote views do not replay the previous run.

## CogMatrix sessions

Every run is recorded in CogMatrix by the rig itself, with the CogMatrix token
cogmoteGO serves on loopback (`mxbiflow.infra.cogmatrix_sync`). When the game
loop starts, mxbiflow creates the session with `create_from_device`, using:

- every animal of the cogmote experiment config as a subject;
- the protocol picked in cogmote and the experiment repository's git version
  as its implementation;
- the operator from the config.

When the game loop quits, mxbiflow ends the session and uploads each animal's
`result.jsonl` and the session snapshot to the storage repository picked in
cogmote. Every step is kept under `.mxbiflow/state/cogmatrix/` until CogMatrix
has it, so a run that started offline or whose uploads failed is completed in
the background of the next run. Without an experiment config in cogmote the run
is not recorded.

## Camera recording

With **Record the camera** on in the device's cogmote configuration
(`recording.record_camera`), the rig records its own camera during the game
loop (`mxbiflow.infra.camera_recording`). MediaMTX serves the Pi camera on path
`mystream`; mxbiflow switches its recording on and off through MediaMTX's
loopback API (`PATCH /v3/config/paths/patch/mystream`). MediaMTX writes fMP4
segments to `~/recordings/mystream/` (CHiPmxbi/setup configures it, with the
device code and time burned into the image).

At the end of the run mxbiflow writes a WebVTT subtitle file next to each
segment with one cue per published trial (trial, animal, `stage@level`,
result), uploads the segments and subtitles to the session after its results
as `camera-<segment>.mp4` and `.vtt`, and deletes them locally once uploaded.
A cue's time is the trial time minus the capture of the segment's first frame:
the segment start in its name minus `recording.capture_latency_ms`, the delay
from the camera to MediaMTX, measured once by filming a millisecond clock.

## Run end

When the game loop quits, `run_experiment` finishes the run without a confirm
step (cagelab/cogmote#424):

- the run summary (per animal: trials, accuracy, duration, stage levels) goes to
  cogmoteGO's `run-summary` broadcast;
- the steps after the run (end the CogMatrix session, upload the results,
  upload the camera recording, send the report) go to the device status as
  `steps`, with `state: finishing`, then `failed` when a step failed, else
  `idle`. Failed CogMatrix steps are retried at the next start; a failed
  report is not;
- the rig screen shows both until the steps are done, then 15 seconds longer.

The report is sent when the `quit` command asked for it (`send_report`, from
cogmote's stop dialog), else when the session config's `send_email` does. The
next run clears the steps and the summary. A crash marks the status `failed`
with a failed `run` step.

## Reports

Crash reports (`mxbiflow.infra.send_crash_report`) and "run not started"
notices are plain-text notifications sent through cogmoteGO's
`POST /notifications`, cut to the 10 KB limit.

The daily session report (`mxbiflow.ui.run_session_post_processing`) is a
structured report sent with pymoteGO's `Client.report` through cogmoteGO's
`POST /reports`: an overview (session details, then per animal its trials,
sessions, duration, stages and levels) followed by one section per stage from
its `StagePostProcessor`. A post-processor returns `PostProcessingResult(blocks,
figures)`: pymoteGO blocks (`Heading`, `Paragraph`, `KeyValue`, `Table`,
`Image`) and PNG figures keyed by the names its `Image` blocks use; draw them
with `matplotlib.figure.Figure` and convert with
`mxbiflow.infra.post_processing.figure_png`. cogmote shows the report with its
figures on the device's report page and emails subscribers the blocks with a
link there. Limits: 200 blocks and 20 figures of at most 2 MiB per report.
Experiment data stays on the device.

## Installation

mxbiflow is no longer published to PyPI; depend on it through a git source
pinned to a commit:

```shell
uv add "mxbiflow @ git+https://github.com/CHiPmxbi/mxbiflow.git@<commit>"
```

Some of its dependencies (pymoteGO, py-mx-eye) are private git repositories,
so the installing machine needs read access to them.

Hardware interfaces and drivers are available under `mxbiflow.driver`:

```python
from mxbiflow.driver import MXBI, MXBIModel
from mxbiflow.driver.detector import DetectorEvent
from mxbiflow.driver.eyetracker import Eyetracker, MxEyeEyetracker
```

An `eyetracker` is configured through the optional `eyetrackers` list of
`config/mxbi.json` (for example `{"type": "mx_eye", "id": 0, "enabled": true}`)
and read at runtime through `get_mxbiflow().mxbi.eyetracker`, which is `None`
when no eyetracker is configured. The `mx_eye` backend streams through
py-mx-eye; until that tracker reports a screen-space mapping, its samples carry
the pupil centre in source-image pixels.

Scenes consume gaze once per frame through `get_mxbiflow().eye_sample`, which
is `None` when no usable sample is available. See
[docs/eyetracking.md](docs/eyetracking.md) for the data flow, the `None`
semantics and a per-frame example.

The former `pymxbi` package is now part of mxbiflow. Replace imports such as
`pymxbi.detector` with `mxbiflow.driver.detector`; no compatibility namespace
is installed.

## Requirements

- Python 3.14+
- pygame-ce and PySide6
