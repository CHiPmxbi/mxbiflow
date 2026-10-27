# Remote Control

The game loop registers the command proxy `mxbiflow` with the local cogmoteGO
(`pymotego.CommandProxy`) and runs its commands once per frame, with the same
actions as the [keyboard shortcuts](shortcuts.md). cogmote and agents send a
command as the JSON body of `POST /api/proxies/mxbiflow/requests` on cogmoteGO
(`control` level). cogmoteGO answers `{"result": "ok"}` once the game loop has
received the command, also for invalid commands, which the game loop logs and
ignores.

When cogmoteGO is not running, the game loop keeps going and retries the
connection every 5 seconds.

| Body | Action |
| --- | --- |
| `{"command": "level_up"}` | Level up the current animal's stage. |
| `{"command": "level_down"}` | Level down; no-op at level 0. |
| `{"command": "next_stage"}` | Next stage in the animal's `stage_order`. |
| `{"command": "prev_stage"}` | Previous stage in the animal's `stage_order`. |
| `{"command": "switch_stage", "stage": "<name>"}` | Move the current animal to any registered stage. |
| `{"command": "reward", "duration_ms": 500}` | Give a manual reward on rewarder 0 (1–10000 ms). |
| `{"command": "pause"}` | Show IDLE and start no task; a running trial is aborted. |
| `{"command": "resume"}` | Resume scheduling; the present animal's task starts. |
| `{"command": "screenshot"}` | Save a screenshot to the session screenshot directory. |
| `{"command": "quit", "send_report": true}` | End the run, as `Esc` does. `send_report` (optional) overrides the session config's `send_email` for the report after the run; cogmote's stop dialog sends it. |

Level and stage commands act on the animal currently at the device and are
no-ops when none is present.

On the rig, through the loopback listener:

```bash
curl -X POST http://127.0.0.1:9011/api/proxies/mxbiflow/requests -d '{"command": "pause"}'
```
