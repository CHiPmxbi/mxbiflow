# Remote Control

The game loop registers the command proxy `mxbiflow` with the local cogmoteGO
(`pymotego.CommandProxy`) and runs its commands once per frame. When it
connects, it describes every command it accepts: a name, a title, an optional
description, a JSON Schema for the params and whether to confirm. cogmote
lists them from `GET /api/proxies` on cogmoteGO and renders one control per
command, with a form for its params. Nothing in cogmoteGO or cogmote knows
mxbiflow's commands.

Commands are pydantic models in a `CommandRegistry` (`mxbiflow.commands`).
The registry builds the descriptions (`model_json_schema()` for the params)
and a discriminated union that validates every command it receives before the
handler runs. mxbiflow's built-in commands and an experiment's own are
registered the same way and have no privileges over each other.

When cogmoteGO is not running, the game loop keeps going and retries the
connection every 5 seconds.

## Sending a command

`POST /api/proxies/mxbiflow/requests` on cogmoteGO (`control` level) with
`{"command": <name>, "params": {...}}`. cogmoteGO rejects unknown commands
and params that fail the schema with a 400 before they reach the game loop.
The reply is `{"ok": bool, "message"?: string, "data"?: any}`: `ok: false`
means the params were invalid or the handler failed, and `message` says why.

On the rig, through the loopback listener:

```bash
curl -X POST http://127.0.0.1:9011/api/proxies/mxbiflow/requests \
  -H 'Content-Type: application/json' -d '{"command": "pause"}'
```

## Built-in commands

| Command | Params | Action |
| --- | --- | --- |
| `level_up` | | Level up the current animal's stage. |
| `level_down` | | Level down; no-op at level 0. |
| `next_stage` | | Next stage in the animal's `stage_order`. |
| `prev_stage` | | Previous stage in the animal's `stage_order`. |
| `switch_stage` | `stage`: one of the registered stages | Move the current animal to any registered stage. |
| `reward` | `duration_ms`: 1–10000 | Give a manual reward on rewarder 0. |
| `pause` | | Show IDLE and start no task; a running trial is aborted. |
| `resume` | | Resume scheduling; the present animal's task starts. |
| `screenshot` | | Save a screenshot to the session screenshot directory. |
| `quit` | | End the run, as `Esc` does; cogmote asks to confirm. |

Level and stage commands act on the animal currently at the device and are
no-ops when none is present. The keyboard [shortcuts](shortcuts.md) run the
same actions.

## Experiment commands

An experiment registers its own commands on the `SceneManager` next to its
stages. A handler gets the validated params model and returns a `Reply`, or
`None` for `ok`; an exception replies `ok: false` with its message and the
run goes on. Handlers run in the game loop between frames, so they may change
scene or session state but must return quickly.

```python
from typing import Literal

from mxbiflow import Reply, SceneManager
from pydantic import BaseModel, Field


class HintParams(BaseModel):
    side: Literal["left", "right"] = Field(title="Side")


scene_manager = SceneManager()
scene_manager.register([...])


@scene_manager.commands.command(
    "show_hint", title="Show hint", params=HintParams,
    description="Flash the correct target once.",
)
def show_hint(params: HintParams) -> Reply:
    ...
    return Reply(message=f"hint on the {params.side}")
```

`params` defaults to `NoParams` (a command without params); `confirm=True`
makes cogmote ask before sending. Names must be unique across built-in and
experiment commands and match `^[A-Za-z0-9._-]{1,64}$`.
