from datetime import UTC
from pathlib import Path

from pymotego.email import EmailClient
from pymxbi.mxbi.factory import MXBIModel

from mxbiflow import set_base_path
from mxbiflow.bootstrap import init_gameloop
from mxbiflow.core.config_store import ConfigStore
from mxbiflow.core.path import get_email_state_path, get_mxbi_config_path
from mxbiflow.infra.post_processing import HtmlComposer, session_overview, summarize
from mxbiflow.models.session import EmailSendStateStore
from mxbiflow.scene import SceneManager
from mxbiflow.scene.idle.idle import IDLE
from mxbiflow.ui.wizard import config_wizard


def main() -> None:
    set_base_path(Path.cwd())

    scene_manager = SceneManager()
    scene_manager.register([IDLE])

    config_wizard(scene_manager)

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
    email_store = EmailSendStateStore(get_email_state_path())
    prev_state = email_store.load()

    with EmailClient() as client:
        result = client.send(
            subject=f"{mxbi_config.mxbi_id} Daily Report",
            html_body=html,
            in_reply_to=prev_state.message_id if prev_state.message_id else None,
        )
        email_store.save(result.message_id)


if __name__ == "__main__":
    main()
