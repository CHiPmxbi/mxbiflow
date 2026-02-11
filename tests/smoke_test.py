import subprocess


def main() -> None:
    import pymxbi

    assert pymxbi.__name__ == "pymxbi"

    from pymxbi.mxbi import MXBI, MXBIModel, build_mxbi, get_mxbi, set_mxbi # noqa: F401

    from pymxbi.detector import (  # noqa: F401
        Detector,
        DetectorEnum,
        DetectorModel,
        MockDetector,
        MockDetectorModel,
        StandardGateDetector,
        RFIDContinuousDetector,
        RFIDContinuousDetectorModel,
        BeambreakContinuousDetector,
        BeamBreakContinuousDetectorModel,
        FusionContinuousDetector,
        FusionContinuousDetectorModel,
        detectors,
    )

    from pymxbi.rewarder import (  # noqa: F401
        Rewarder,
        RewarderEnum,
        RewarderModel,
        MockRewarder,
        MockRewarderModel,
        RPIGpioRewarder,
        GPIORewarderModel,
        rewarders,
    )

    subprocess.run(["pymxbi", "--help"], check=True, capture_output=True, text=True)


if __name__ == "__main__":
    main()
