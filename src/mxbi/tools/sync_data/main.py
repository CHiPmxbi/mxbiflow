import typer
from mxbi.tools.sync_data.setup_samba import setup_samba
from mxbi.tools.sync_data.sync_data import sync_data

app = typer.Typer()


@app.command()
def sync() -> None:
    sync_data()


@app.command()
def setup() -> None:
    setup_samba()

if __name__ == "__main__":
    app()
