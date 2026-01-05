from pathlib import Path
from typing import Literal

from pydantic import BaseModel, field_validator


class Trial(BaseModel):
    trial_id: str
    trial_number: int
    subject_id: str
    partner_id: str

    call_identity_id: str
    call_category: str
    is_partner_call: bool

    other_identity_id: str
    other_category: str

    partner_side: Literal["left", "right"]
    correct_side: Literal["left", "right"]

    audio_identity_id: str
    audio_index: int
    audio_path: str

    left_image_identity_id: str
    left_image_index: int
    left_image_path: str

    right_image_identity_id: str
    right_image_index: int
    right_image_path: str

    seed: int | None = None

    @field_validator("partner_side", "correct_side")
    @classmethod
    def _normalize_sides(cls, v: str) -> str:
        lv = v.strip().lower()
        if lv not in {"left", "right"}:
            raise ValueError("side must be 'left' or 'right'")
        return lv

    @field_validator("is_partner_call", mode="before")
    @classmethod
    def _boolify(cls, v):
        if isinstance(v, bool):
            return v
        if isinstance(v, int):
            return bool(v)
        if isinstance(v, str):
            lv = v.strip().lower()
            if lv in {"true", "t", "yes", "y", "1"}:
                return True
            if lv in {"false", "f", "no", "n", "0"}:
                return False
        raise ValueError("is_partner_call must be boolean-like")

    def audio_path_obj(self, base: Path | None = None) -> Path:
        p = Path(self.audio_path)
        return (base / p) if base and not p.is_absolute() else p

    def left_image_path_obj(self, base: Path | None = None) -> Path:
        p = Path(self.left_image_path)
        return (base / p) if base and not p.is_absolute() else p

    def right_image_path_obj(self, base: Path | None = None) -> Path:
        p = Path(self.right_image_path)
        return (base / p) if base and not p.is_absolute() else p
