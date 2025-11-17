def main() -> None:
    from mxbi.theater import Theater
    from mxbi.tmp_post_porcess import HabituationTrainingStagePostProcess
    from mxbi.tools.sync_data.sync_data import sync_data
    from mxbi.ui.launch_panel import LaunchPanel

    LaunchPanel()

    theater = Theater()
    data_paths = theater.data_path

    HabituationTrainingStagePostProcess(data_paths)
    sync_data()


if __name__ == "__main__":
    main()
