import datetime
import subprocess

import typer
from rich import print

from mxbi.path import (
    DATA_DIR_PATH,
    SAMBA_BACKUP_DIR_PATH,
    SAMBA_MOUNT_PATH,
)


def sync_data() -> None:
    """Sync local data to Samba share with automatic backup of changed files."""
    if not DATA_DIR_PATH.exists():
        print(
            f"[bold red]❌ Local data directory not found:[/bold red] {DATA_DIR_PATH}"
        )
        raise typer.Exit(1)

    if not SAMBA_MOUNT_PATH.is_mount():
        print(f"[bold red]❌ Samba share is not mounted:[/bold red] {SAMBA_MOUNT_PATH}")
        raise typer.Exit(1)

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
        f"{DATA_DIR_PATH}/",  # source
        f"{SAMBA_MOUNT_PATH}/",  # destination
    ]

    print("[cyan]🔄 Syncing data to Samba share...[/cyan]")
    result = subprocess.run(rsync_cmd)

    if result.returncode == 0:
        print("[bold green]✅ Sync completed successfully![/bold green]")
    else:
        print(f"[bold red]❌ Sync failed (exit {result.returncode}).[/bold red]")
        raise typer.Exit(result.returncode)
