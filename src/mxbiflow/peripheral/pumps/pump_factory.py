from enum import StrEnum, auto

from mxbi.peripheral.pumps.mock_pump import MockPump
from mxbi.peripheral.pumps.rasberrypi_gpio_pump import RasberryPiGPIOPump
from mxbi.peripheral.pumps.rewarder import Rewarder


class PumpEnum(StrEnum):
    MOCK = auto()
    RASBERRY_PI_GPIO = auto()


DEFAULT_PUMP = PumpEnum.RASBERRY_PI_GPIO


class PumpFactory:
    """Factory responsible for creating rewarder instances."""

    pumps: dict[PumpEnum, type[Rewarder]] = {
        PumpEnum.MOCK: MockPump,
        PumpEnum.RASBERRY_PI_GPIO: RasberryPiGPIOPump,
    }

    @classmethod
    def create(cls, rewarder_type: PumpEnum) -> Rewarder:
        rewarder_cls = cls.pumps[rewarder_type]
        return rewarder_cls()
