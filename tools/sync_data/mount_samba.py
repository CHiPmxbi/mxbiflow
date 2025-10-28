import subprocess
import sys

import keyring
import typer
from models import samba_config
from rich import print

from tools.sync_data.constant import KEYRING_SERVICE_NAME, SAMBA_MOUNT_PATH


def mount_samba() -> bool:
    username, server, share_path, password = resolve_samba_credentials()

    mount_point = SAMBA_MOUNT_PATH
    mount_point.mkdir(parents=True, exist_ok=True)

    already_mounted = (
        subprocess.run(["mountpoint", "-q", str(mount_point)], check=False).returncode
        == 0
    )
    if already_mounted:
        print(f"Samba share already mounted at {mount_point}")
        return True

    mount_cmd = [
        "mount",
        "-t",
        "cifs",
        f"//{server}/{share_path.lstrip('/')}",
        str(mount_point),
        "-o",
        f"username={username},password={password}",
    ]

    result = subprocess.run(mount_cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        error_output = (result.stderr or result.stdout or "").strip() or "no output"
        print(f"Mount failed (exit {result.returncode}): {error_output}")
        return False

    print(f"Samba share mounted at {mount_point}")
    return True


def resolve_samba_credentials(
    require_password: bool = True,
) -> tuple[str, str, str, str]:
    config = samba_config.value

    username = (config.username or "").strip()
    server = (config.server or "").strip()
    share_path = (config.share_path or "").strip()

    if not username or not server or not share_path:
        print(
            "Missing Samba configuration; run 'python tools/sync_data.py setup'.",
            file=sys.stderr,
        )
        raise typer.Exit(1)

    password = keyring.get_password(KEYRING_SERVICE_NAME, username)
    if require_password and not password:
        print(
            f"No password stored in keyring for user '{username}'. Run the setup command first.",
            file=sys.stderr,
        )
        raise typer.Exit(1)

    resolved_password = password or ""

    return username, server, share_path, resolved_password
