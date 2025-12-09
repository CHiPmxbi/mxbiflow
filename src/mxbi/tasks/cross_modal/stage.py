import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Final

from mxbi.data_logger import DataLogger
from mxbi.utils.logger import logger

from mxbi.tasks.cross_modal.models import CrossModalOutcome, CrossModalResultRecord
from mxbi.tasks.cross_modal.scene import (
    CrossModalScene,
    CrossModalResult,
)
from mxbi.tasks.cross_modal.trial_io import TrialStore, read_trials

if TYPE_CHECKING:
    from mxbi.models.animal import AnimalState
    from mxbi.models.session import SessionState
    from mxbi.models.task import Feedback
    from mxbi.theater import Theater


class CrossModalTask:
    STAGE_NAME: Final[str] = "cross_modal_task"

    def __init__(
        self,
        theater: "Theater",
        session_state: "SessionState",
        animal_state: "AnimalState",
    ) -> None:
        self._theater = theater
        self._session_state = session_state
        self._animal_state = animal_state
        self._screen = session_state.session_config.screen_type

        cfg = session_state.session_config

        trial_file_str = getattr(cfg, "cross_modal_trial_file", None)
        if not trial_file_str:
            raise RuntimeError(
                "cross_modal_trial_file is not configured in SessionConfig. "
                "Set it via the launcher for cross_modal_task."
            )

        media_root_str = getattr(cfg, "cross_modal_media_root", None)
        self._base_dir = Path(media_root_str) if media_root_str else None

        mock_env = os.environ.get("MXBI_MOCK", "0").strip().lower()
        self._mock = mock_env in {"1", "true", "yes", "y"}
        self._mock_strategy = os.environ.get("MXBI_MOCK_STRATEGY", "always_correct")
        self._mock_latency_ms = int(os.environ.get("MXBI_MOCK_LATENCY_MS", "1000"))

        verify_paths = not self._mock

        trial_path = Path(trial_file_str)
        self._trial_store: TrialStore = read_trials(
            trial_path,
            verify_paths=verify_paths,
            base_dir=self._base_dir,
        )

        self._trial, self._trial_index = self._trial_store.next_for_subject(
            self._animal_state.name
        )

        self._scene = CrossModalScene(
            theater=self._theater,
            session_state=self._session_state,
            animal_state=self._animal_state,
            screen=self._screen,
            trial=self._trial,
            base_dir=self._base_dir,
        )

        self._data_logger = DataLogger(
            self._session_state, self._animal_state.name, self.STAGE_NAME
        )
        self._feedback = False

    def start(self) -> "Feedback":
        result = self._scene.start()
        self._feedback = result.feedback

        if not result.cancelled:
            self._log_trial(result)

        self._trial_store.advance(self._animal_state.name, self._trial_index)

        logger.debug(
            "cross_modal_task: session_id=%s, subject=%s, level=%s, "
            "csv_index=%s, is_partner=%s, feedback=%s",
            getattr(self._session_state, "session_id", None),
            self._animal_state.name,
            self._animal_state.level,
            self._trial_index + 1,
            self._trial.is_partner_call,
            self._feedback,
        )
        return self._feedback

    def quit(self) -> None:
        self._scene.cancel()

    def on_idle(self) -> None:
        self._scene.cancel()

    def on_return(self) -> None:
        self._scene.cancel()

    @property
    def condition(self):
        return None

    def _log_trial(self, result: CrossModalResult) -> None:
        try:
            if result.timeout:
                outcome = CrossModalOutcome.TIMEOUT
            elif result.cancelled:
                outcome = CrossModalOutcome.ABORTED
            elif result.feedback:
                outcome = CrossModalOutcome.CORRECT
            else:
                outcome = CrossModalOutcome.INCORRECT

            if (
                result.trial_start_time is not None
                and result.choice_time is not None
                and not result.timeout
            ):
                latency = result.choice_time - result.trial_start_time
            else:
                latency = None

            if result.chosen_side == "left":
                chosen_identity = self._trial.left_image_identity_id
            elif result.chosen_side == "right":
                chosen_identity = self._trial.right_image_identity_id
            else:
                chosen_identity = None

            rec = CrossModalResultRecord(
                timestamp=time.time(),
                session_id=getattr(self._session_state, "session_id", None),
                subject_id=self._trial.subject_id,
                partner_id=self._trial.partner_id,
                trial_id=self._trial.trial_id,
                trial_number=self._trial.trial_number,
                call_identity_id=self._trial.call_identity_id,
                call_category=self._trial.call_category,
                is_partner_call=self._trial.is_partner_call,
                other_identity_id=self._trial.other_identity_id,
                other_category=self._trial.other_category,
                partner_side=self._trial.partner_side,
                correct_side=self._trial.correct_side,
                audio_identity_id=self._trial.audio_identity_id,
                audio_index=self._trial.audio_index,
                audio_path=self._trial.audio_path,
                left_image_identity_id=self._trial.left_image_identity_id,
                left_image_index=self._trial.left_image_index,
                left_image_path=self._trial.left_image_path,
                right_image_identity_id=self._trial.right_image_identity_id,
                right_image_index=self._trial.right_image_index,
                right_image_path=self._trial.right_image_path,
                chosen_side=result.chosen_side,
                chosen_identity_id=chosen_identity,
                outcome=outcome,
                trial_start_time=result.trial_start_time,
                choice_time=result.choice_time,
                latency_sec=latency,
                choice_x=result.choice_x,
                choice_y=result.choice_y,
                aborted=result.cancelled,
                timeout=result.timeout,
            )

            payload = rec.model_dump()
            self._data_logger.save_jsonl(payload)
            self._data_logger.save_csv_row(payload)
        except Exception:
            logger.exception("Failed to log cross-modal trial")