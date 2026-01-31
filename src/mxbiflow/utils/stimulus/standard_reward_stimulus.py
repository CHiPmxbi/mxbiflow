from math import ceil
from typing import TYPE_CHECKING

from numpy import int16

from mxbi.utils.aplayer import ToneConfig

if TYPE_CHECKING:
    from concurrent.futures import Future

    from numpy.typing import NDArray

    from mxbi.theater import Theater

STIMULUS_FREQUENCY = 2000
STIMULUS_FREQUENCY_DURATION = 100
STIMULUS_FREQUENCY_INTERVAL = 100


class StandardRewardStimulus:
    def __init__(self, stimulus_duration: int, theater: "Theater") -> None:
        self._stimulus_duration = stimulus_duration
        self._theater = theater

        self._tone = self._gen()

    def _gen(self) -> "NDArray[int16]":
        unit_duration = STIMULUS_FREQUENCY_DURATION + STIMULUS_FREQUENCY_INTERVAL

        times = ceil(self._stimulus_duration / unit_duration)
        times = max(times, 1)

        freq_1 = ToneConfig(
            frequency=STIMULUS_FREQUENCY,
            duration=STIMULUS_FREQUENCY_DURATION,
        )

        freq_2 = ToneConfig(
            frequency=0,
            duration=STIMULUS_FREQUENCY_INTERVAL,
        )

        return self._theater.aplayer.generate_stimulus([freq_1, freq_2], times)

    def play(self, reward_duration: int) -> None:
        future = self._theater.aplayer.play_stimulus(self._tone)
        future.add_done_callback(lambda f: self._reward(f, reward_duration))

    def _reward(self, future: "Future", reward_duration: int) -> None:
        if future.result():
            self._theater.reward.give_reward(reward_duration)
