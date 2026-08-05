from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Screen:
    width: int
    height: int

    @property
    def center(self) -> tuple[int, int]:
        xshift = self.width * 0.25 * 0.75
        return int(self.width * 0.5 + xshift), int(self.height * 0.5)
