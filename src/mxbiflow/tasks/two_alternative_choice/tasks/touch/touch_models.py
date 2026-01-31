from mxbi.tasks.two_alternative_choice.models import (
    BaseDataToShow,
    BaseTrialConfig,
    BaseTrialData,
)


class TrialConfig(BaseTrialConfig):
    stimulus_freq: int
    stimulus_freq_duration: int

    stimulus_interval: int


class TrialData(BaseTrialData):
    trial_config: TrialConfig


class DataToShow(BaseDataToShow): ...
