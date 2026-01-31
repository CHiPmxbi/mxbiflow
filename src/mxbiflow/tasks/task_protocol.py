from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from mxbi.models.animal import AnimalState, ScheduleCondition
    from mxbi.models.session import SessionState
    from mxbi.models.task import Feedback
    from mxbi.theater import Theater


class Task(Protocol):
    def __init__(
        self,
        theater: "Theater",
        session_state: "SessionState",
        animal_state: "AnimalState",
    ) -> None: ...
    def start(self) -> "Feedback": ...

    def quit(self) -> None: ...

    def on_idle(self) -> None: ...

    def on_return(self) -> None: ...

    @property
    def condition(self) -> "ScheduleCondition | None": ...
