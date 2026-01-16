import subprocess


def main() -> None:
    import pymxbi

    assert pymxbi.__name__ == "pymxbi"

    from pymxbi.detector.detector import (  # noqa: F401
        DetectionResult,
        Detector,
        DetectorEvent,
        DetectorState,
    )
    from pymxbi.rewarder.rewarder import Rewarder  # noqa: F401

    subprocess.run(["pymxbi", "--help"], check=True, capture_output=True, text=True)


if __name__ == "__main__":
    main()
