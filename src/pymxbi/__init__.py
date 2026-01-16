import typer

app = typer.Typer()


@app.command()
def setup_samba():
    from pymxbi.tools.setup_samba.setup_samba import setup_samba

    setup_samba()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
