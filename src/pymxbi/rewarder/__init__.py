from .rewarder import Rewarder, RewarderEnum
from .mock_rewarder import MockRewarder
from .rpi_gpio_rewarder import RPIGpioRewarder


rewarders: dict[str, type[Rewarder]] = {
    RewarderEnum.MOCK: MockRewarder,
    RewarderEnum.RPI_GPIO: RPIGpioRewarder,
}


__all__ = ["Rewarder", "MockRewarder", "RPIGpioRewarder", "RewarderEnum", "rewarders"]
