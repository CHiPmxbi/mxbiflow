import os
import platform
from enum import StrEnum, auto

from mxbi.utils.logger import logger


class PlatformEnum(StrEnum):
    WINDOWS = auto()
    LINUX = auto()
    MACOS = auto()
    RASPBERRY = auto()


def detect_current_platform() -> PlatformEnum:
    if platform.system() == "Windows":
        return PlatformEnum.WINDOWS
    elif platform.system() == "Linux":
        if is_raspberry_pi():
            return PlatformEnum.RASPBERRY
        else:
            return PlatformEnum.LINUX

    elif platform.system() == "Darwin":
        return PlatformEnum.MACOS

    else:
        raise NotImplementedError("Platform not supported")


def is_raspberry_pi() -> bool:
    try:
        with open("/proc/cpuinfo", "r") as f:
            cpuinfo = f.read().lower()
            if "raspberry pi" in cpuinfo or "bcm" in cpuinfo:
                return True

        if os.path.exists("/proc/device-tree/model"):
            with open("/proc/device-tree/model", "r") as f:
                model = f.read().lower()
                if "raspberry pi" in model:
                    return True

        if os.path.exists("/sys/firmware/devicetree/base/model"):
            with open("/sys/firmware/devicetree/base/model", "r") as f:
                model = f.read().lower()
                if "raspberry pi" in model:
                    return True

    except (IOError, OSError) as e:
        logger.error(f"Error reading device tree: {e}")

    return False


if __name__ == "__main__":
    current_platform = detect_current_platform()
    print(current_platform)
