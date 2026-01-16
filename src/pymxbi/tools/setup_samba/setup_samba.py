"""Set up a systemd unit to mount a Samba (CIFS) share.

This module provides an interactive workflow (via Typer prompts) to generate a
systemd ``.service`` unit that mounts a Samba share with in-memory credentials.
Credentials are encrypted using ``systemd-creds`` and embedded into the unit.

Notes
-----
Most operations require elevated privileges (e.g. linking into
``/etc/systemd/system`` and running ``systemctl``).
"""

import os
import subprocess
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path

import typer
from rich import print


@dataclass(frozen=True)
class SambaMountConfig:
    """Configuration for a Samba mount systemd unit.

    Parameters
    ----------
    service_name : str
        Base unit name (without the ``.service`` suffix).
    service_path : pathlib.Path
        Full path to the generated unit file (including the ``.service`` suffix).
    mount_path : pathlib.Path
        Local absolute path where the share will be mounted.
    smb_server : str
        UNC path to the share (e.g. ``//storage.local/share/path``).
    username : str
        Username used to authenticate to the share.
    password : str
        Password used to authenticate to the share.
    domain : str, optional
        Domain used to authenticate to the share.
    uid : int, optional
        Local user ID that should own files in the mounted share.
    gid : int, optional
        Local group ID that should own files in the mounted share.
    """

    service_name: str  # base name, e.g. "dpz-smb-mount" (NO ".service")
    service_path: Path  # full path to unit file (with ".service")
    mount_path: Path
    smb_server: str
    username: str
    password: str
    domain: str = ""
    uid: int = 1000
    gid: int = 1000

    @property
    def unit_filename(self) -> str:
        return f"{self.service_name}.service"

    @property
    def cred_name(self) -> str:
        # tie cred name to service to avoid collisions
        return f"{self.service_name}.cred"


def setup_samba(
    mount_path: Path | None = None,
    service_name: str | None = None,
    service_path: Path | None = None,
) -> None:
    """Interactively configure and install a Samba mount systemd unit.

    Prompts for any missing values, then generates the unit file, links it into
    ``/etc/systemd/system``, reloads systemd, and starts/enables the unit.

    Parameters
    ----------
    mount_path : pathlib.Path or None, optional
        Local absolute path where the share will be mounted. If not provided,
        the user is prompted.
    service_name : str or None, optional
        Systemd unit base name. The ``.service`` suffix is optional; it will be
        normalized away. If not provided, the user is prompted.
    service_path : pathlib.Path or None, optional
        Destination path for the generated unit file. If not provided, the user
        is prompted.

    Raises
    ------
    typer.Exit
        If input validation fails or if any required system command fails.
    """
    service_name = _normalize_service_name(service_name or _prompt_service_name())
    service_path = service_path or _prompt_service_path(service_name)
    mount_path = mount_path or _prompt_mount_path()

    cfg = _prompt_smb_config(service_name, service_path, mount_path)
    create_unit(cfg)
    link_unit(cfg)
    enable_unit(cfg)


def _normalize_service_name(name: str) -> str:
    """Normalize a systemd unit name.

    Parameters
    ----------
    name : str
        Unit name, optionally ending with ``.service``.

    Returns
    -------
    str
        Normalized base name without the ``.service`` suffix.
    """
    name = name.strip()
    if name.endswith(".service"):
        name = name[: -len(".service")]
    return name


def _prompt_mount_path() -> Path:
    """Prompt for an absolute local mount path.

    Returns
    -------
    pathlib.Path
        Absolute local mount path.

    Raises
    ------
    typer.Exit
        If the user provides a non-absolute path.
    """
    p = Path(typer.prompt("Enter local mount path (absolute)", default="/mnt/samba"))
    if not p.is_absolute():
        print("[red]❌ Mount path must be absolute (e.g. /mnt/share)[/red]")
        raise typer.Exit(code=1)
    return p


def _prompt_service_name() -> str:
    """Prompt for a base systemd service name.

    Returns
    -------
    str
        Service base name without the ``.service`` suffix.
    """
    return typer.prompt("Enter systemd service name", default="dpz-smb-mount").strip()


def _prompt_service_path(service_name: str) -> Path:
    """Prompt for the output directory and return a unit path.

    Parameters
    ----------
    service_name : str
        Base unit name (without the ``.service`` suffix).

    Returns
    -------
    pathlib.Path
        Full path to the unit file (including the ``.service`` suffix).

    Raises
    ------
    typer.Exit
        If the user provides a non-absolute output directory.
    """
    base_dir = Path.home() / ".config" / "pymxbi" / "services"
    p = Path(
        typer.prompt("Enter unit output dir (absolute)", default=str(base_dir))
    ).expanduser()
    if not p.is_absolute():
        print(
            "[red]❌ Output dir must be absolute (e.g. ~/.config/pymxbi/services)[/red]"
        )
        raise typer.Exit(code=1)
    return p / f"{service_name}.service"


def _prompt_smb_config(
    service_name: str, service_path: Path, mount_path: Path
) -> SambaMountConfig:
    """Prompt for SMB connection details and build a config.

    Parameters
    ----------
    service_name : str
        Base unit name (without the ``.service`` suffix).
    service_path : pathlib.Path
        Full path to the unit file to write.
    mount_path : pathlib.Path
        Local absolute mount path.

    Returns
    -------
    SambaMountConfig
        Completed mount configuration.

    Raises
    ------
    typer.Exit
        If the SMB server path is not a UNC path (does not start with ``//``).
    """
    smb_server = typer.prompt(
        "Enter SMB server (e.g. //storage.local/share/path)"
    ).strip()
    domain = typer.prompt("Enter domain (leave empty if none)", default="").strip()
    username = typer.prompt("Enter username").strip()
    password = getpass("Enter password: ")

    if not smb_server.startswith("//"):
        print("[red]❌ SMB server must start with '//' (UNC path).[/red]")
        raise typer.Exit(code=1)

    uid = os.getuid()
    gid = os.getgid()

    return SambaMountConfig(
        service_name=service_name,
        service_path=service_path,
        mount_path=mount_path,
        smb_server=smb_server,
        domain=domain,
        username=username,
        password=password,
        uid=uid,
        gid=gid,
    )


def _run(
    cmd: list[str], *, input_text: str | None = None, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess command with captured output.

    Parameters
    ----------
    cmd : list[str]
        Command and arguments to execute.
    input_text : str or None, optional
        Text to pass to stdin.
    check : bool, optional
        If ``True``, raise :class:`subprocess.CalledProcessError` on non-zero exit.

    Returns
    -------
    subprocess.CompletedProcess[str]
        Completed process including stdout/stderr.
    """
    return subprocess.run(
        cmd,
        input=input_text,
        text=True,
        capture_output=True,
        check=check,
    )


def _encrypt_creds(cfg: SambaMountConfig) -> str:
    """Encrypt SMB credentials with ``systemd-creds``.

    Parameters
    ----------
    cfg : SambaMountConfig
        Mount configuration containing the plaintext credentials.

    Returns
    -------
    str
        ``systemd-creds encrypt`` output suitable for embedding into the unit.

    Raises
    ------
    typer.Exit
        If ``systemd-creds`` fails.
    """
    creds_lines = []
    if cfg.domain:
        creds_lines.append(f"domain={cfg.domain}")
    creds_lines.append(f"username={cfg.username}")
    creds_lines.append(f"password={cfg.password}")
    creds_text = "\n".join(creds_lines)

    print("[cyan]🔒 Encrypting credentials using systemd-creds...[/cyan]")
    cmd = [
        "sudo",
        "systemd-creds",
        "encrypt",
        "-",
        "-",  # stdin -> stdout
        f"--name={cfg.cred_name}",
        "--pretty",
    ]
    proc = _run(cmd, input_text=creds_text, check=False)
    if proc.returncode != 0:
        print("[red]❌ Failed to run systemd-creds.[/red]")
        print(f"[yellow]STDOUT:[/yellow]\n{proc.stdout.strip()}")
        print(f"[yellow]STDERR:[/yellow]\n{proc.stderr.strip()}")
        raise typer.Exit(code=1)

    print("[green]✅ Credentials encrypted successfully.[/green]")
    return proc.stdout.strip()


def render_unit(cfg: SambaMountConfig, encrypted_block: str) -> str:
    """Render a systemd oneshot unit to mount the share.

    Parameters
    ----------
    cfg : SambaMountConfig
        Mount configuration.
    encrypted_block : str
        Output from ``systemd-creds encrypt`` to embed into the unit.

    Returns
    -------
    str
        The rendered unit text.
    """
    opts = ",".join(
        [
            f"credentials=%d/{cfg.cred_name}",
            f"uid={cfg.uid}",
            f"gid={cfg.gid}",
            "nobrl",
            "_netdev",
        ]
    )

    return f"""[Unit]
Description=Mount Samba Share ({cfg.smb_server})
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes

ExecStart=/usr/bin/mount -t cifs {cfg.smb_server} {cfg.mount_path} -o {opts}
ExecStop=/usr/bin/umount {cfg.mount_path}

{encrypted_block}

[Install]
WantedBy=multi-user.target
"""


def create_unit(cfg: SambaMountConfig) -> None:
    """Create the unit file on disk and encrypt credentials.

    Parameters
    ----------
    cfg : SambaMountConfig
        Mount configuration.

    Raises
    ------
    typer.Exit
        If credential encryption fails or the unit cannot be written.
    """
    print(
        "[bold cyan]=== Create systemd Samba mount service (in-memory credentials) ===[/bold cyan]"
    )

    cfg.mount_path.mkdir(parents=True, exist_ok=True)
    cfg.service_path.parent.mkdir(parents=True, exist_ok=True)

    encrypted_block = _encrypt_creds(cfg)
    unit_text = render_unit(cfg, encrypted_block)

    cfg.service_path.write_text(unit_text, encoding="utf-8")
    os.chmod(cfg.service_path, 0o600)

    print(f"[green]✅ Unit created:[/green] [bold]{cfg.service_path}[/bold]")


def link_unit(cfg: SambaMountConfig) -> None:
    """Link the generated unit into ``/etc/systemd/system``.

    Parameters
    ----------
    cfg : SambaMountConfig
        Mount configuration.

    Raises
    ------
    typer.Exit
        If the symlink cannot be created.
    """
    print("[cyan]🔗 Linking unit into /etc/systemd/system/...[/cyan]")
    target = Path("/etc/systemd/system") / cfg.unit_filename

    try:
        subprocess.run(
            ["sudo", "ln", "-sf", str(cfg.service_path), str(target)], check=True
        )
        print(f"[green]✅ Linked:[/green] {target}")
    except subprocess.CalledProcessError:
        print("[red]❌ Failed to create symlink.[/red]")
        raise typer.Exit(code=1)


def enable_unit(cfg: SambaMountConfig) -> None:
    """Reload systemd, start the unit, and enable it at boot.

    Parameters
    ----------
    cfg : SambaMountConfig
        Mount configuration.

    Raises
    ------
    typer.Exit
        If reloading, starting, or enabling the unit fails.
    """
    unit = cfg.unit_filename
    print("[cyan]⚙️ Reloading systemd daemon and starting unit...[/cyan]")

    try:
        subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)

        start = subprocess.run(
            ["sudo", "systemctl", "start", unit], capture_output=True, text=True
        )
        if start.returncode != 0:
            print("[red]❌ Failed to start unit. Not enabling it.[/red]")
            print(f"[yellow]STDOUT:[/yellow]\n{start.stdout.strip()}")
            print(f"[yellow]STDERR:[/yellow]\n{start.stderr.strip()}")
            raise typer.Exit(code=1)

        subprocess.run(["sudo", "systemctl", "enable", unit], check=True)
        print(f"[green]✅ Enabled on boot:[/green] {unit}")

    except subprocess.CalledProcessError as e:
        print(f"[red]❌ Command failed:[/red] {e}")
        raise typer.Exit(code=1)
