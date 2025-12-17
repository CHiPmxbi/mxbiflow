from enum import StrEnum, auto

from pydantic import BaseModel


class CrossModalOutcome(StrEnum):
    CORRECT = auto()
    INCORRECT = auto()
    TIMEOUT = auto()
    ABORTED = auto()


class CrossModalResultRecord(BaseModel):
    timestamp: float
    session_id: int | None
    subject_id: str
    partner_id: str

    trial_id: str
    trial_number: int

    call_identity_id: str
    call_category: str
    is_partner_call: bool

    other_identity_id: str
    other_category: str

    partner_side: str
    correct_side: str

    audio_identity_id: str
    audio_index: int
    audio_path: str

    left_image_identity_id: str
    left_image_index: int
    left_image_path: str

    right_image_identity_id: str
    right_image_index: int
    right_image_path: str

    chosen_side: str | None
    chosen_identity_id: str | None

    outcome: CrossModalOutcome

    trial_start_time: float | None
    choice_time: float | None
    latency_sec: float | None

    choice_x: int | None
    choice_y: int | None

    aborted: bool
    timeout: bool
