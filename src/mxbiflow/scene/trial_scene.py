"""A stage's trial, with its life cycle kept by the framework."""

from abc import abstractmethod
from typing import final

from pydantic import BaseModel

from ..core.context import get_mxbiflow
from ..gameloop.settlement import (
    CountSettlementConfig,
    RateSettlementConfig,
    SettlementAction,
    settle_by_count,
    settle_by_rate,
)
from ..infra.data_logger import DataLogger
from .scene import Scene


class TrialScene(Scene):
    """One trial of a stage: an instance is made for each trial of the animal's stage.

    The framework counts the trial, and when it ends records it in ``result.jsonl``,
    publishes it, settles the animal's level and stops the trial's timers and sounds.
    The stage describes the trial: :meth:`begin` starts it, the scene's ``handle_event``,
    ``update`` and ``draw`` run it, :meth:`finish` ends it and :meth:`record` describes
    it. A trial the framework ends first (the animal left, the run ended) is
    :attr:`aborted`: recorded and published, but not settled.

    Levels count from 1, as :mod:`mxbiflow.gameloop.settlement` does.
    """

    def __init__(self) -> None:
        super().__init__()
        self.mxbiflow = get_mxbiflow()
        self.session = self.mxbiflow.session
        self.animal = self.session.require_current_animal()
        self.session.add_trial()
        #: The animal's stage, level and trial numbers when the trial started.
        self.info = self.animal.base_info
        #: Whether the trial was correct; ``None`` leaves it out of accuracy.
        self.correct: bool | None = None
        #: The framework ended the trial before the stage finished it.
        self.aborted = False
        #: What settling the trial decided; set before :meth:`record` is called.
        self.action = SettlementAction.NONE
        self._closed = False

    # ---- the stage -----------------------------------------------------------

    @abstractmethod
    def begin(self) -> None:
        """Start the trial."""

    @abstractmethod
    def record(self) -> BaseModel:
        """The trial's record, asked once when the trial has ended."""

    def end(self) -> None:
        """Stop what the trial started; called once, however the trial ends."""

    def settlement(self) -> RateSettlementConfig | CountSettlementConfig | None:
        """The rule that moves the animal between levels; ``None`` keeps the level."""
        return None

    def decide(self) -> SettlementAction:
        """Count the finished trial and decide whether the animal moves.

        By default a trial with :attr:`correct` set counts at its level and is settled
        by :meth:`settlement`.
        """
        if self.correct is None:
            return SettlementAction.NONE
        self.session.count_trial(self.correct)
        rule = self.settlement()
        stage = self.animal.current_stage
        before = stage.level_correct - self.correct
        if isinstance(rule, RateSettlementConfig):
            return settle_by_rate(
                self.correct, before, stage.level_counted, stage.level, rule
            ).action
        if isinstance(rule, CountSettlementConfig):
            return settle_by_count(self.correct, 0, before, stage.level, rule).action
        return SettlementAction.NONE

    def move(self, action: SettlementAction) -> None:
        """Move the animal as settled; the trial is already recorded."""
        match action:
            case SettlementAction.LEVEL_UP:
                self.session.level_up()
            case SettlementAction.LEVEL_DOWN:
                self.session.level_down()
            case SettlementAction.NEXT_STAGE:
                self.session.go_next_stage()
            case SettlementAction.PREV_STAGE:
                self.session.go_prev_stage()
            case SettlementAction.NONE:
                pass

    # ---- the framework -------------------------------------------------------

    @final
    def start(self) -> None:
        self._running = True
        self.begin()

    @final
    def finish(self, correct: bool | None) -> None:
        """End the trial; the stage calls this once."""
        self.correct = correct
        self._close(aborted=False)

    @final
    def quit(self) -> None:
        if self._running:
            self._close(aborted=True)

    def _close(self, *, aborted: bool) -> None:
        if self._closed:
            return
        self._closed = True
        self._running = False
        self.aborted = aborted
        self.end()
        self.mxbiflow.timer.cancel_all()
        self.mxbiflow.mxbi.aplayer.cancel_all()
        if not aborted:
            self.action = self.decide()
        record = self.record()
        DataLogger(self.session, animal=self.animal.name, stage=self.name()).save(
            record.model_dump(mode="json")
        )
        # Published before the animal moves, so the event carries the trial's stage.
        self.mxbiflow.publish_trial(record, correct=self.correct)
        self.move(self.action)
