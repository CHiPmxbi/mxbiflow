def main() -> None:
    import mxbiflow.driver

    assert mxbiflow.driver.__name__ == "mxbiflow.driver"

    from mxbiflow.driver.detector import (  # noqa: F401
        BeambreakContinuousDetector,
        BeamBreakContinuousDetectorModel,
        Detector,
        DetectorEnum,
        DetectorModel,
        FusionContinuousDetector,
        FusionContinuousDetectorModel,
        MockDetector,
        MockDetectorModel,
        RFIDContinuousDetector,
        RFIDContinuousDetectorModel,
    )
    from mxbiflow.driver.mxbi import (  # noqa: F401
        MXBI,
        MXBIModel,
        build_mxbi,
        get_mxbi,
        set_mxbi,
    )
    from mxbiflow.driver.rewarder import (  # noqa: F401
        GPIORewarderModel,
        MockRewarder,
        MockRewarderModel,
        Rewarder,
        RewarderEnum,
        RewarderModel,
        RPIGpioRewarder,
        rewarders,
    )


if __name__ == "__main__":
    main()
