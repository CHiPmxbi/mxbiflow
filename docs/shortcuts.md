# Keyboard Shortcuts

This document lists the keyboard shortcuts supported by the MXBI game loop.
All shortcuts are registered centrally in
`src/mxbiflow/gameloop/shortcuts.py` via `register_default_shortcuts`.

| Key | Action | Notes |
| --- | --- | --- |
| `Esc` | Quit the game | Stops the game loop and cleans up the session. |
| `q` | Quit the game | Same as `Esc`. |
| `c` | Capture a screenshot | Saved to the session screenshot directory. |
| `0` – `5` | Simulate the RFID animal at the corresponding index entering | Index follows the configured animal map order; only effective with a mock detector. |
| `l` | Simulate the current animal leaving | Only effective with a mock detector. |

## Adding a new shortcut

1. Add the binding in `register_default_shortcuts` with
   `registry.register(key, description, handler)`.
2. Document the key in the table above.
3. Add a matching dispatch test in `tests/test_shortcuts.py`.

Duplicate keys are rejected with `ValueError` at registration time.
