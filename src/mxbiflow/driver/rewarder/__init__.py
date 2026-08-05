from typing import Annotated, Literal

from pydantic import BaseModel, Field

from .mock_rewarder import MockRewarder
from .rewarder import Rewarder, RewarderEnum
from .rpi_gpio_rewarder import RPIGpioRewarder

rewarders: dict[str, type[Rewarder]] = {
    RewarderEnum.MOCK: MockRewarder,
    RewarderEnum.RPI_GPIO: RPIGpioRewarder,
}


class MockRewarderModel(BaseModel):
    type: Literal[RewarderEnum.MOCK] = RewarderEnum.MOCK
    id: int = Field(default=0, ge=0)

    enabled: bool = False

    @property
    def device_type(self) -> str:
        return str(self.type)


class GPIORewarderModel(BaseModel):
    type: Literal[RewarderEnum.RPI_GPIO] = RewarderEnum.RPI_GPIO
    id: int = Field(default=0, ge=0)

    enabled: bool = False

    pin: int = Field(default=13, ge=0)

    @property
    def device_type(self) -> str:
        return str(self.type)


type RewarderModel = Annotated[
    GPIORewarderModel | MockRewarderModel,
    Field(discriminator="type"),
]


__all__ = [
    "GPIORewarderModel",
    "MockRewarder",
    "MockRewarderModel",
    "RPIGpioRewarder",
    "Rewarder",
    "RewarderEnum",
    "RewarderModel",
    "rewarders",
]
