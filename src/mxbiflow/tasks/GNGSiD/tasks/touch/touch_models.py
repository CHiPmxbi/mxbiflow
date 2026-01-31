from mxbi.tasks.GNGSiD.models import BaseDataToShow, BaseTrialConfig, BaseTrialData


class TrialConfig(BaseTrialConfig):
    stimulus_freq: int
    stimulus_freq_duration: int
    stimulus_freq_master_amp: int
    stimulus_freq_digital_amp: int

    stimulus_interval: int


class TrialData(BaseTrialData):
    trial_config: TrialConfig


class DataToShow(BaseDataToShow): ...
