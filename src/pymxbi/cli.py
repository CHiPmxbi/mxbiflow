import typer

app = typer.Typer()


@app.command()
def setup_samba():
    from .tools.setup_samba.setup_samba import setup_samba

    setup_samba()


def main() -> None:
    app()
