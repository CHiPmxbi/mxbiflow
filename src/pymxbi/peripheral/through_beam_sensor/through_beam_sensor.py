from typing import Protocol


class ThroughBeamSensor(Protocol):
    def read(self) -> int: ...

    def close(self) -> None: ...
