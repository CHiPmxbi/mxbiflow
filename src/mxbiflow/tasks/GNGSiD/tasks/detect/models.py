from mxbi.tasks.GNGSiD.models import BaseDataToShow, BaseTrialConfig, BaseTrialData


class TrialConfig(BaseTrialConfig):
    go: bool
    visual_stimulus_delay: int

    stimulus_freq: int
    stimulus_freq_duration: int
    stimulus_freq_master_amp: int
    stimulus_freq_digital_amp: int

    stimulus_interval: int


class TrialData(BaseTrialData):
    trial_config: TrialConfig


class DataToShow(BaseDataToShow):
    stimulus: bool
