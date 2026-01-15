"""Helpers for syncing files via `rsync`."""

from pathlib import Path
import subprocess
import shlex


def rsync_one_way(source: Path, destination: Path) -> None:
    """Copy files from `source` into mounted `destination` via `rsync`.

    Parameters
    ----------
    source : pathlib.Path
        Local directory to copy from.
    destination : pathlib.Path
        Mounted destination directory to copy into.

    Returns
    -------
    None

    Raises
    ------
    FileNotFoundError
        If `source` does not exist, is not a directory, `destination` does not exist,
        is not a directory, or `destination` is not a mount point.
    RuntimeError
        If `rsync` returns a non-zero exit code.

    Notes
    -----
    This uses `rsync` with the following behavior:

    - Copies directories recursively and preserves modification times.
    - Does not preserve permissions/ownership (`--no-perms`, `--no-owner`, `--no-group`).
    - Does not cross filesystem boundaries (`--one-file-system`).
    - Does not overwrite existing destination files (`--ignore-existing`).

    `rsync` must be available on the system `PATH`.
    """
    if not source.exists():
        raise FileNotFoundError(f"Source path does not exist: {source}")
    if not source.is_dir():
        raise FileNotFoundError(f"Source path is not a directory: {source}")

    if not destination.exists():
        raise FileNotFoundError(f"Destination path does not exist: {destination}")
    if not destination.is_dir():
        raise FileNotFoundError(f"Destination path is not a directory: {destination}")
    if not destination.is_mount():
        raise FileNotFoundError(f"Destination path is not a mount point: {destination}")

    rsync_cmd = [
        "rsync",
        "--recursive",  # recurse into directories
        "--times",  # preserve modification times
        "--no-perms",  # do not preserve permissions
        "--no-owner",  # do not preserve ownership
        "--no-group",  # do not preserve group
        "--one-file-system",  # do not cross filesystem boundaries
        "--human-readable",  # readable file sizes
        "--info=stats2,progress2",  # detailed progress and stats
        "--ignore-existing",  # do not update existing files
        "--itemize-changes",  # show changes for updated files
        f"{source}/",  # source
        f"{destination}/",  # destination
    ]

    try:
        subprocess.run(rsync_cmd, check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"rsync failed with exit code {e.returncode}\n"
            f"command: {shlex.join(rsync_cmd)}"
        ) from e
