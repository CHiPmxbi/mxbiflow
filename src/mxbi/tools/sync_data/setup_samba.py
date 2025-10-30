#!/usr/bin/env python3
import subprocess
from getpass import getpass

import typer
from mxbi.path import MOUNT_SERVICE_NAME, MOUNT_SERVICE_PATH, SAMBA_MOUNT_PATH
from rich import print


def setup_samba() -> None:
    create()
    link()
    enable()


def link() -> None:
    """
    Link the generated systemd service file into /etc/systemd/system/
    """
    print("[cyan]🔗 Linking service file to /etc/systemd/system/...[/cyan]")

    target_path = f"/etc/systemd/system/{MOUNT_SERVICE_NAME}"

    try:
        subprocess.run(
            ["sudo", "ln", "-sf", str(MOUNT_SERVICE_PATH), target_path],
            check=True,
        )
        print(f"[green]✅ Linked:[/green] {target_path}")
    except subprocess.CalledProcessError:
        print(
            "[red]❌ Failed to create symlink. Try running with sudo privileges.[/red]"
        )
        raise typer.Exit(code=1)


def enable() -> None:
    """
    Reload systemd, test-start the service once, and enable only if it starts successfully.
    """
    print("[cyan]⚙️ Reloading systemd daemon and testing service start...[/cyan]")

    try:
        # Reload systemd units
        subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)

        # Try to start the service first (without enabling)
        print(f"[cyan]▶️ Testing start for:[/cyan] {MOUNT_SERVICE_NAME}")
        start_proc = subprocess.run(
            ["sudo", "systemctl", "start", f"{MOUNT_SERVICE_NAME}"],
            capture_output=True,
            text=True,
        )

        if start_proc.returncode != 0:
            print("[red]❌ Failed to start the service. Not enabling it.[/red]")
            print(f"[yellow]STDOUT:[/yellow]\n{start_proc.stdout.strip()}")
            print(f"[yellow]STDERR:[/yellow]\n{start_proc.stderr.strip()}")
            raise typer.Exit(code=1)

        print("[green]✅ Service started successfully.[/green]")

        # Enable the service to start automatically on boot
        print("[cyan]🔁 Enabling service to start on boot...[/cyan]")
        subprocess.run(
            ["sudo", "systemctl", "enable", f"{MOUNT_SERVICE_NAME}"],
            check=True,
        )

        print(f"[green]✅ Service enabled on boot:[/green] {MOUNT_SERVICE_NAME}")

    except subprocess.CalledProcessError as e:
        print(f"[red]❌ Command failed:[/red] {e}")
        raise typer.Exit(code=1)


def create() -> None:
    print(
        "[bold cyan]=== Create systemd Samba mount service (in-memory credentials) ===[/bold cyan]"
    )

    # ---- Interactive input ----
    smb_server = typer.prompt(
        "Enter SMB server address (e.g. //storage.dpz.local/share/path)"
    )
    domain = typer.prompt("Enter domain (leave empty if none)", default="")
    username = typer.prompt("Enter username")
    password = getpass("Enter password: ")

    # ---- Basic validation ----
    if not smb_server.startswith("//"):
        print(
            "[red]❌ Invalid input: server must start with '//' and mount point must be absolute.[/red]"
        )
        raise typer.Exit(code=1)

    # ---- Ensure mount directory exists ----
    SAMBA_MOUNT_PATH.mkdir(parents=True, exist_ok=True)

    # ---- Build credentials in memory ----
    creds = []
    if domain:
        creds.append(f"domain={domain}")
    creds.append(f"username={username}")
    creds.append(f"password={password}")
    creds_text = "\n".join(creds)

    # ---- Encrypt credentials using systemd-creds ----
    print("[cyan]🔒 Encrypting credentials using systemd-creds...[/cyan]")
    cmd = [
        "sudo",
        "systemd-creds",
        "encrypt",
        "-",
        "-",
        "--name=dpz-smb-cred",
        "--pretty",
    ]

    result = subprocess.run(
        cmd,
        input=creds_text,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print("[red]❌ Failed to run systemd-creds.[/red]")
        print(f"[yellow]STDOUT:[/yellow]\n{result.stdout.strip()}")
        print(f"[yellow]STDERR:[/yellow]\n{result.stderr.strip()}")
        raise typer.Exit(code=1)

    encrypted_block = result.stdout.strip()
    print("[green]✅ Credentials encrypted successfully.[/green]")

    # ---- Generate systemd service content ----
    service_content = f"""[Unit]
Description=Mount Samba Share ({smb_server})
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes

ExecStartPre=/bin/sleep 60
ExecStart=/usr/bin/mount -t cifs {smb_server} {SAMBA_MOUNT_PATH} -o credentials=%d/dpz-smb-cred,uid=1000,gid=1000,nobrl,_netdev
ExecStop=/usr/bin/umount {SAMBA_MOUNT_PATH}

{encrypted_block}

[Install]
WantedBy=multi-user.target
"""

    # ---- Write service file ----
    MOUNT_SERVICE_PATH.parent.mkdir(parents=True, exist_ok=True)
    MOUNT_SERVICE_PATH.write_text(service_content, encoding="utf-8")

    print(
        f"\n[green]✅ Systemd service file created:[/green] [bold]{MOUNT_SERVICE_PATH}[/bold]"
    )
    print("[bold cyan]👉 Next steps:[/bold cyan]")
    print("   sudo systemctl daemon-reload")
    print(f"   sudo systemctl enable {MOUNT_SERVICE_NAME}.service")
    print(f"   sudo systemctl start {MOUNT_SERVICE_NAME}.service")
