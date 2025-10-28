import keyring
import typer
from constant import KEYRING_SERVICE_NAME
from models import samba_config


def setup_samba() -> None:
    """
    Prompt for Samba server details and credentials, storing them in the config and keyring.
    """
    resolved_service = KEYRING_SERVICE_NAME
    typer.echo(f"Saving Samba credentials to keyring service '{resolved_service}'.")
    config = samba_config.value
    server = _prompt_with_default(
        "Samba server address (e.g. 192.168.1.10)", config.server
    )
    share_path = _prompt_with_default(
        "Samba share path (e.g. shared/data)", config.share_path
    )
    username = _prompt_with_default("Username", config.username)
    password = _prompt_with_default("Password", hide_input=True)

    keyring.set_password(resolved_service, username, password)
    _store_config(username=username, server=server, share_path=share_path)

    typer.echo("Credentials stored successfully.")


def _store_config(username: str, server: str, share_path: str) -> None:
    config = samba_config.value
    config.username = username
    config.server = server
    config.share_path = share_path
    samba_config.save()


def _prompt_with_default(
    message: str, default: str | None = None, hide_input: bool = False
) -> str:
    if default:
        return typer.prompt(message, default=default, hide_input=hide_input).strip()
    return typer.prompt(message, hide_input=hide_input).strip()
