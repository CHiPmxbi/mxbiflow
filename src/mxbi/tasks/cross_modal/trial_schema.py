from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, field_validator, model_validator


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

    seed: str

    @model_validator(mode="before")
    @classmethod
    def _from_bundle_trial(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values

        if "trialId" not in values:
            return values

        audio = values.get("audio") if isinstance(values.get("audio"), dict) else {}
        left_image = values.get("leftImage") if isinstance(values.get("leftImage"), dict) else {}
        right_image = values.get("rightImage") if isinstance(values.get("rightImage"), dict) else {}

        return {
            "trial_id": values.get("trialId"),
            "trial_number": values.get("trialNumber"),
            "subject_id": values.get("subjectId"),
            "partner_id": values.get("partnerId"),
            "call_identity_id": values.get("callIdentityId"),
            "call_category": values.get("callCategory"),
            "is_partner_call": values.get("isPartnerCall"),
            "other_identity_id": values.get("otherIdentityId"),
            "other_category": values.get("otherCategory"),
            "partner_side": values.get("partnerSide"),
            "correct_side": values.get("correctSide"),
            "audio_identity_id": audio.get("identityId"),
            "audio_index": audio.get("exemplarIndex"),
            "audio_path": audio.get("path"),
            "left_image_identity_id": left_image.get("identityId"),
            "left_image_index": left_image.get("exemplarIndex"),
            "left_image_path": left_image.get("path"),
            "right_image_identity_id": right_image.get("identityId"),
            "right_image_index": right_image.get("exemplarIndex"),
            "right_image_path": right_image.get("path"),
            "seed": values.get("seed"),
        }

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
