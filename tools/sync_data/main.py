import typer
from mount_samba import mount_samba
from setup_samba import setup_samba
from sync_data import sync_data

app = typer.Typer()


@app.command()
def sync() -> None:
    sync_data()


@app.command()
def setup() -> None:
    setup_samba()


@app.command()
def mount() -> None:
    if not mount_samba():
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
