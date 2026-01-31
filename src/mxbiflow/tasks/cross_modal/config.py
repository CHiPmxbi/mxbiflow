import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from mxbi.path import CROSS_MODAL_CONFIG_PATH


class CrossModalVisualConfig(BaseModel):
    image_scale: float = Field(default=0.5, ge=0.1, le=0.9)


class CrossModalAudioConfig(BaseModel):
    master_volume: int = Field(default=70, ge=0, le=100)
    digital_volume: int = Field(default=70, ge=0, le=100)
    gain: float = Field(default=1.0, ge=0.0, le=4.0)
    wav_rate_policy: Literal["resample", "error"] = "resample"


class CrossModalTimingConfig(BaseModel):
    fixation_ms: int = Field(default=300, ge=0, le=10_000)
    trial_timeout_ms: int = Field(default=10_000, ge=1_000, le=120_000)


class CrossModalConfig(BaseModel):
    visual: CrossModalVisualConfig = Field(default_factory=CrossModalVisualConfig)
    audio: CrossModalAudioConfig = Field(default_factory=CrossModalAudioConfig)
    timing: CrossModalTimingConfig = Field(default_factory=CrossModalTimingConfig)


def load_cross_modal_config(path: Path = CROSS_MODAL_CONFIG_PATH) -> CrossModalConfig:
    if not path.exists():
        raise FileNotFoundError(f"Cross-modal config not found: {path}")
    return CrossModalConfig.model_validate_json(path.read_text(encoding="utf-8"))


def save_cross_modal_config(
    config: CrossModalConfig, path: Path = CROSS_MODAL_CONFIG_PATH
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.model_dump(), indent=4), encoding="utf-8")
