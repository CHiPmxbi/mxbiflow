from __future__ import annotations

from dataclasses import dataclass
from time import time
from tkinter import CENTER, Canvas, Event
from typing import TYPE_CHECKING, Final

from PIL import Image, ImageTk
from mxbi.tasks.cross_modal.media import load_wav_as_int16
from mxbi.utils.logger import logger
from mxbi.utils.tkinter.components.canvas_with_border import CanvasWithInnerBorder
from mxbi.utils.tkinter.components.showdata_widget import ShowDataWidget

if TYPE_CHECKING:
    from mxbi.models.animal import AnimalState
    from mxbi.models.session import ScreenConfig, SessionState
    from src.mxbi.tasks.cross_modal.trial_schema import Trial
    from mxbi.theater import Theater


@dataclass
class CrossModalResult:
    chosen_side: str | None
    timeout: bool
    feedback: bool
    cancelled: bool
    trial_start_time: float | None
    choice_time: float | None
    choice_x: int | None
    choice_y: int | None


class CrossModalScene:
    TRIAL_TIMEOUT_MS: Final[int] = 10_000

    def __init__(
        self,
        theater: "Theater",
        session_state: "SessionState",
        animal_state: "AnimalState",
        screen: "ScreenConfig",
        trial: "Trial",
        base_dir: "Path | None" = None,
    ) -> None:
        self._theater = theater
        self._session_state = session_state
        self._animal_state = animal_state
        self._screen = screen
        self._trial = trial
        self._base_dir = base_dir

        self._background: CanvasWithInnerBorder | None = None
        self._left_canvas: Canvas | None = None
        self._right_canvas: Canvas | None = None
        self._left_image: ImageTk.PhotoImage | None = None
        self._right_image: ImageTk.PhotoImage | None = None
        self._show_data_widget: ShowDataWidget | None = None

        self._chosen_side: str | None = None
        self._timeout = False
        self._feedback = False
        self._cancelled = False

        self._trial_start_time: float | None = None
        self._choice_time: float | None = None
        self._choice_x: int | None = None
        self._choice_y: int | None = None

    def start(self) -> CrossModalResult:
        self._create_view()
        self._bind_events()
        self._play_audio()
        self._theater.mainloop()
        return CrossModalResult(
            chosen_side=self._chosen_side,
            timeout=self._timeout,
            feedback=self._feedback,
            cancelled=self._cancelled,
            trial_start_time=self._trial_start_time,
            choice_time=self._choice_time,
            choice_x=self._choice_x,
            choice_y=self._choice_y,
        )

    def cancel(self) -> None:
        if self._cancelled:
            return
        self._cancelled = True
        self._feedback = False
        self._timeout = False
        self._stop_and_close()

    def _create_view(self) -> None:
        self._background = CanvasWithInnerBorder(
            master=self._theater.root,
            bg="black",
            width=self._screen.width,
            height=self._screen.height,
            border_width=40,
        )
        self._background.place(relx=0.5, rely=0.5, anchor="center")
        self._background.focus_set()

        self._show_data_widget = ShowDataWidget(self._background)
        self._show_data_widget.place(relx=0, rely=1, anchor="sw")
        self._show_data_widget.show_data(
            {
                "name": self._animal_state.name,
                "id": self._animal_state.trial_id,
                "level_id": self._animal_state.current_level_trial_id,
                "level": self._animal_state.level,
                "rewards": 0,
                "correct": self._animal_state.correct_trial,
                "incorrect": 0,
                "timeout": 0,
            }
        )

        self._background.create_text(
            self._screen.width / 2,
            self._screen.height / 2,
            text="+",
            fill="white",
            font=("Helvetica", 40),
        )
        self._background.after(300, self._show_images)

    def _show_images(self) -> None:
        if self._background is None:
            return

        self._background.delete("all")

        img_size = int(min(self._screen.width, self._screen.height) * 0.35)

        self._left_canvas = Canvas(
            self._background, width=img_size, height=img_size, bg="grey", highlightthickness=0
        )
        self._left_canvas.place(relx=0.25, rely=0.5, anchor=CENTER)

        self._right_canvas = Canvas(
            self._background, width=img_size, height=img_size, bg="grey", highlightthickness=0
        )
        self._right_canvas.place(relx=0.75, rely=0.5, anchor=CENTER)

        if self._left_canvas is not None:
            self._left_canvas.bind("<ButtonPress-1>", lambda e: self._on_choice("left", e))
        if self._right_canvas is not None:
            self._right_canvas.bind("<ButtonPress-1>", lambda e: self._on_choice("right", e))

        left_path = self._trial.left_image_path_obj(self._base_dir)
        right_path = self._trial.right_image_path_obj(self._base_dir)

        try:
            img = Image.open(left_path).resize((img_size, img_size), Image.LANCZOS)
            self._left_image = ImageTk.PhotoImage(img)
            self._left_canvas.create_image(img_size // 2, img_size // 2, image=self._left_image)
        except Exception:
            logger.exception("Failed to load left image %s", left_path)
            self._left_canvas.create_text(
                img_size // 2, img_size // 2, text=self._trial.left_image_identity_id, fill="white"
            )

        try:
            img = Image.open(right_path).resize((img_size, img_size), Image.LANCZOS)
            self._right_image = ImageTk.PhotoImage(img)
            self._right_canvas.create_image(img_size // 2, img_size // 2, image=self._right_image)
        except Exception:
            logger.exception("Failed to load right image %s", right_path)
            self._right_canvas.create_text(
                img_size // 2, img_size // 2, text=self._trial.right_image_identity_id, fill="white"
            )

        self._background.create_text(
            self._screen.width * 0.25,
            self._screen.height * 0.8,
            text=f"Left: {self._trial.left_image_identity_id}",
            fill="white",
        )
        self._background.create_text(
            self._screen.width * 0.75,
            self._screen.height * 0.8,
            text=f"Right: {self._trial.right_image_identity_id}",
            fill="white",
        )

        self._trial_start_time = time()
        self._background.after(self.TRIAL_TIMEOUT_MS, self._on_timeout)

    def _bind_events(self) -> None:
        if self._background is None:
            return
        self._background.bind("<r>", lambda e: self._give_manual_reward())
        self._background.bind("<s>", lambda e: self._theater.caputre(self._background))

    def _play_audio(self) -> None:
        ap = self._trial.audio_path_obj(self._base_dir)
        try:
            stim = load_wav_as_int16(ap)
        except Exception:
            logger.exception("Failed to load WAV file %s", ap)
            return
        self._theater.aplayer.play_stimulus(stim)

    def _on_choice(self, side: str, event: Event) -> None:
        if self._cancelled or self._chosen_side is not None:
            return
        self._chosen_side = side
        self._choice_time = time()
        self._choice_x = event.x_root
        self._choice_y = event.y_root
        self._timeout = False
        self._feedback = side == self._trial.correct_side
        self._stop_and_close()

    def _on_timeout(self) -> None:
        if self._cancelled or self._chosen_side is not None:
            return
        self._chosen_side = None
        self._timeout = True
        self._feedback = False
        self._stop_and_close()

    def _stop_and_close(self) -> None:
        self._theater.aplayer.stop()
        if self._background is not None:
            try:
                self._background.destroy()
            except Exception:
                pass
            self._background = None
        try:
            self._theater.root.quit()
        except Exception:
            pass

    def _give_manual_reward(self) -> None:
        self._theater.reward.give_reward(500)