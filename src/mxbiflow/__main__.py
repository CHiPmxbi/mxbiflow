from datetime import UTC
from pathlib import Path

from pymotego.email import EmailClient
from pymxbi.mxbi.factory import MXBIModel

from mxbiflow import set_base_path
from mxbiflow.bootstrap import init_gameloop
from mxbiflow.core.config_store import ConfigStore
from mxbiflow.core.path import get_mxbi_config_path, get_runtime_state_path
from mxbiflow.infra.post_processing import HtmlComposer, session_overview, summarize
from mxbiflow.models.session import RuntimeStateStore
from mxbiflow.scene import SceneManager
from mxbiflow.scene.idle.idle import IDLE
from mxbiflow.ui import run_wizard


def main() -> None:
    set_base_path(Path.cwd())

    scene_manager = SceneManager()
    scene_manager.register([IDLE])

    if not run_wizard(scene_manager):
        return

    game = init_gameloop(scene_manager)
    game.play()

    summary = summarize()

    date_str = (
        summary.start_at.astimezone(UTC).strftime("%Y-%m-%d")
        if summary.start_at
        else "N/A"
    )
    composer = HtmlComposer(
        title=f"Session #{summary.session_id}",
        date=date_str,
    )
    composer.add_section(session_overview())

    html = composer.html

    mxbi_config = ConfigStore(get_mxbi_config_path(), MXBIModel).value
    runtime_store = RuntimeStateStore(get_runtime_state_path())
    previous_message_id = runtime_store.email_message_id

    with EmailClient() as client:
        result = client.send(
            subject=f"{mxbi_config.mxbi_id} Daily Report",
            html_body=html,
            in_reply_to=previous_message_id or None,
        )
        runtime_store.save_email_message_id(result.message_id)


if __name__ == "__main__":
    main()
