# Eye Tracking

mxbiflow reads gaze through the `eyetracker` device of the driver layer. The
configured backend owns a background reader thread; the game loop never blocks
on the tracker.

## Data flow

```
MxEyeEyetracker reader thread              Game.play() frame (60 Hz)
  MxEye.read(timeout=poll_timeout)   ┌─ pygame events  → scene_manager.handle_event
  → keep the latest fresh sample     ├─ scene_manager.update(dt) → Scene.update(dt_s)
                                     ├─ aplayer.update / scheduler.update
                                     ├─ mxbiflow.update()          (FrameTimer only)
                                     └─ draw → apply_pending
```

The reader thread stores the latest sample, `sample()` drops anything older
than `max_age_ms`, and the game loop simply asks for the current value when it
needs it. Gaze is a continuous "latest value" signal, so it is consumed by
pulling rather than by posting a pygame event per sample: a 60–100 Hz stream
turned into events would flood the event queue, while sparse device events
(see `DetectorBridge`) exist for state transitions.

The SDK subscribes asynchronously, so starting before the tracker publishes is
not an error: gaze simply stays `None` until samples arrive. It has no
compatibility layer, so `py-mx-eye` is pinned in `pyproject.toml` to the SDK
contract this driver consumes.

## Consuming gaze per frame

Scenes read `MXBIFlow.eye_sample` from `update(dt_s)`. The value is `None`
whenever there is no usable gaze for that frame:

| Situation | `eye_sample` |
| --- | --- |
| No `eyetracker` configured (or `enabled: false`) | `None` |
| Tracker running, pupil detected | The latest `EyeSample` |
| No sample yet | `None` |
| Tracker configured but not publishing (offline, or acquisition stopped) | `None` |
| Latest sample older than `max_age_ms` | `None` |
| Sample stream stopped or tracker unreachable | `None` |
| Pupil not detected in the frame (NaN coordinates) | `None` |

A scene that needs gaze should cache the context once and reset its own
accumulators whenever the sample is missing:

```python
from mxbiflow import Scene, get_mxbiflow


class GazeDwell(Scene):
    def __init__(self) -> None:
        super().__init__()
        self._mxbiflow = get_mxbiflow()
        self._dwell_s = 0.0

    def update(self, dt_s: float) -> None:
        sample = self._mxbiflow.eye_sample
        if sample is None or not self._is_on_target(sample):
            self._dwell_s = 0.0
            return

        self._dwell_s += dt_s
        if self._dwell_s >= self._dwell_threshold_s:
            self._on_gaze_held()
```

Code outside a scene (for example a helper invoked from `update`) can reach the
same data through `get_mxbiflow().mxbi.eyetracker.sample()`, which returns
`None` when no eyetracker is configured.

## Coordinates

`EyeSample.x`/`y` are meant to be screen-space gaze coordinates, but py-mx-eye
does not deliver that mapping yet: the `mx_eye` backend currently reports the
pupil centre in source-image pixels (`pupil_x`/`pupil_y`). Do not implement
target hit-testing on those values — they are only useful for relative pupil
displacement or dwell on raw movement. When the tracker exposes screen-space
coordinates, the change stays inside `MxEyeEyetracker.sample()`.

## Not supported yet

- **Per-frame snapshot.** `eye_sample` is read live, so a sample that arrives
  between `update()` and `draw()` can be seen as a slightly newer value by
  `draw()`. If strict intra-frame consistency is ever required, `MXBIFlow`
  would sample once per frame in `MXBIFlow.update()` and cache it, and
  `Game.play()` would have to call `mxbiflow.update()` before
  `scene_manager.update(dt)` instead of after it (otherwise scenes would read
  the previous frame's value). Scenes would not change.
- **Fixation / dwell detection.** Accumulating time, hit-testing and reward
  decisions stay in the experiment's scenes.
- **Gaze logging.** Samples are not persisted to the session data yet.
