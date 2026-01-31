import time
from pathlib import Path
from typing import TYPE_CHECKING, Final

from PIL import Image

from mxbi.data_logger import DataLogger
from mxbi.tasks.cross_modal.bundle_dir import CrossModalBundleDir
from mxbi.tasks.cross_modal.config import CrossModalConfig, load_cross_modal_config
from mxbi.tasks.cross_modal.media import load_wav_as_int16
from mxbi.tasks.cross_modal.models import CrossModalOutcome, CrossModalResultRecord
from mxbi.tasks.cross_modal.scene import CrossModalResult, CrossModalScene
from mxbi.tasks.cross_modal.trial_io import TrialCursor
from mxbi.utils.logger import logger

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

    from mxbi.models.animal import AnimalState
    from mxbi.models.session import SessionState
    from mxbi.models.task import Feedback
    from mxbi.theater import Theater
    from PIL.Image import Image as PILImage


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

        bundle_dir_str = getattr(session_state.session_config, "cross_modal_bundle_dir", None)
        if not bundle_dir_str:
            raise RuntimeError(
                "No cross-modal bundle directory configured. "
                "Set session_config.cross_modal_bundle_dir via the launcher."
            )

        bundle_root = Path(bundle_dir_str).expanduser().resolve()
        self._bundle_dir = CrossModalBundleDir.from_dir_path(bundle_root)

        subject_id = self._animal_state.name
        trials = self._bundle_dir.load_trials(subject_id)
        if not trials:
            raise RuntimeError(f"Bundle contains zero trials for subject '{subject_id}'.")

        self._cursor = TrialCursor(bundle_root=self._bundle_dir.root_dir, subject_id=subject_id)
        self._trial_index = self._cursor.next_index(len(trials))
        self._trial = trials[self._trial_index]

        self._cross_modal_config: CrossModalConfig = load_cross_modal_config()

        image_size = int(
            min(self._screen.width, self._screen.height)
            * self._cross_modal_config.visual.image_scale
        )

        left_image_path = self._bundle_dir.resolve_media_path(self._trial.left_image_path)
        right_image_path = self._bundle_dir.resolve_media_path(self._trial.right_image_path)
        audio_path = self._bundle_dir.resolve_media_path(self._trial.audio_path)

        left_image = self._prepare_image(
            left_image_path,
            image_size=image_size,
        )
        right_image = self._prepare_image(
            right_image_path,
            image_size=image_size,
        )

        audio_stimulus = load_wav_as_int16(
            audio_path,
            rate_policy=self._cross_modal_config.audio.wav_rate_policy,
            gain=self._cross_modal_config.audio.gain,
        )

        self._scene = CrossModalScene(
            theater=self._theater,
            session_state=self._session_state,
            animal_state=self._animal_state,
            screen=self._screen,
            trial=self._trial,
            cross_modal_config=self._cross_modal_config,
            left_image=left_image,
            right_image=right_image,
            audio_stimulus=audio_stimulus,
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

        self._cursor.advance(self._trial_index)

        logger.debug(
            "cross_modal_task: session_id=%s, subject=%s, level=%s, "
            "trial_index=%s, is_partner=%s, feedback=%s",
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

    @staticmethod
    def _prepare_image(image_path: Path, *, image_size: int) -> "PILImage":
        with Image.open(image_path) as img:
            prepared = img.convert("RGB").rotate(90, expand=True)
            prepared = prepared.resize((image_size, image_size), Image.LANCZOS)
            return prepared
