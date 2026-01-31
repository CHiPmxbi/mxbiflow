from mxbi.tasks.GNGSiD.models import BaseDataToShow, BaseTrialConfig, BaseTrialData


class TrialConfig(BaseTrialConfig):
    is_stimulus_trial: bool
    visual_stimulus_delay: int

    medium_reward_duration: int
    medium_reward_threshold: int
    low_reward_duration: int

    attention_duration: int
    extra_response_time: int

    stimulus_freq_high: int
    stimulus_freq_high_duration: int
    stimulus_freq_high_master_amp: int
    stimulus_freq_high_digital_amp: int
    stimulus_freq_low: int
    stimulus_freq_low_duration: int
    stimulus_freq_low_master_amp: int
    stimulus_freq_low_digital_amp: int
    stimulus_interval: int


class TrialData(BaseTrialData):
    trial_config: TrialConfig


class DataToShow(BaseDataToShow):
    stimulus: bool
