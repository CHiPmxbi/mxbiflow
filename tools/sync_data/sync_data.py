import datetime
import subprocess
import sys

import typer
from mount_samba import mount_samba
from rich import print

from tools.sync_data.constant import (
    DATA_DIR_PATH,
    SAMBA_BACKUP_DIR_PATH,
    SAMBA_MOUNT_PATH,
)


def sync_data() -> None:
    """Synchronize local data to the Samba share, with backup of updated files."""
    if not DATA_DIR_PATH.exists():
        print(
            f"[bold red]❌ Local data directory does not exist:[/bold red] {DATA_DIR_PATH}",
            file=sys.stderr,
        )
        raise typer.Exit(1)

    mounted = mount_samba()
    if not mounted:
        print(
            "[bold red]❌ Failed to mount Samba share. Aborting sync.[/bold red]",
            file=sys.stderr,
        )
        raise typer.Exit(1)

    # Create timestamped backup subdir
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    rsync_cmd = [
        "rsync",
        "--archive",  # preserve attributes and recurse
        "--verbose",  # detailed output
        "--compress",  # compress data during transfer
        "--human-readable",  # readable file sizes
        "--progress",  # show progress bar
        "--backup",  # keep old versions of changed files
        f"--backup-dir={SAMBA_BACKUP_DIR_PATH}_{timestamp}",  # backup directory
        f"{DATA_DIR_PATH}/",  # source (with trailing slash)
        f"{SAMBA_MOUNT_PATH}/",  # destination (with trailing slash)
    ]

    try:
        result = subprocess.run(
            rsync_cmd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        print(
            "[bold red]❌ rsync not found. Please install rsync and try again.[/bold red]",
            file=sys.stderr,
        )
        raise typer.Exit(1)

    if result.returncode != 0:
        print(
            f"[bold red]❌ rsync failed (exit {result.returncode}):[/bold red]\n{result.stderr}",
            file=sys.stderr,
        )
        raise typer.Exit(result.returncode)

    print(result.stdout)
