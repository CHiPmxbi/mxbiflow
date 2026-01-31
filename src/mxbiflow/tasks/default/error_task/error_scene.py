from tkinter import Canvas
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mxbi.models.animal import AnimalState, ScheduleCondition
    from mxbi.models.session import SessionState
    from mxbi.models.task import Feedback
    from mxbi.theater import Theater


class ErrorScene:
    def __init__(
        self,
        theater: "Theater",
        session_state: "SessionState",
        animal_state: "AnimalState",
    ) -> None:
        self._theater = theater
        self._session_config = session_state
        self._screen_type = self._session_config.session_config.screen_type

        self._on_trial_start()

    def _on_trial_start(self) -> None:
        self._create_view()

    def _create_view(self) -> None:
        self._background = Canvas(
            self._theater.root,
            bg="red",
            width=self._screen_type.width,
            height=self._screen_type.height,
            highlightthickness=0,
        )
        self._background.place(relx=0.5, rely=0.5, anchor="center")

    def start(self) -> "Feedback":
        self._theater.root.mainloop()

        return True

    def quit(self) -> None:
        self._background.destroy()
        self._theater.root.quit()

    def on_idle(self) -> None:
        self.quit()

    def on_return(self) -> None: ...

    @property
    def condition(self) -> "ScheduleCondition | None":
        return None
