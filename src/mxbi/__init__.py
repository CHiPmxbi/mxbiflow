def main() -> None:
    from mxbi.theater import Theater
    from mxbi.tools.sync_data.sync_data import sync_data
    from mxbi.ui.launch_panel import LaunchPanel

    LaunchPanel()

    Theater()

    sync_data()


if __name__ == "__main__":
    main()
