from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from loguru import logger
from pydantic import BaseModel

from ..models.animal import AnimalSessionState
from ..models.session import Session
from .notify import notify


class StageSummary(BaseModel):
    name: str
    trials: int
    initial_level: int
    final_level: int


class AnimalSummary(BaseModel):
    name: str
    rfid_tags: tuple[str, ...] = ()
    total_trials: int
    animal_sessions: int
    total_duration_seconds: float
    stages: list[StageSummary]


class SessionSummary(BaseModel):
    session_id: int
    start_at: datetime | None
    end_at: datetime | None
    duration_seconds: float
    experimenter: str = ""
    reward_type: str
    total_animals: int
    note: str = ""
    animals: list[AnimalSummary]


@dataclass(frozen=True)
class PostProcessingResult:
    """One stage's section of the plain-text session report."""

    text: str


class StagePostProcessor(ABC):
    @abstractmethod
    def process(
        self,
        session: Session,
        stage_data_paths: Mapping[str, Path],
    ) -> PostProcessingResult:
        """Build the report section for one stage."""


def _format_timestamp(dt: datetime | None) -> str:
    if dt is None:
        return "N/A"

    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _format_duration(seconds: float) -> str:
    if seconds <= 0:
        return "N/A"
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _format_level(stage: StageSummary) -> str:
    change = stage.final_level - stage.initial_level
    if change == 0:
        return f"level {stage.initial_level} (no change)"
    return f"level {stage.initial_level} -> {stage.final_level} ({change:+d})"


def _calc_animal_duration(sessions: Sequence[AnimalSessionState]) -> float:
    total = 0.0
    for s in sessions:
        if s.start_at and s.end_at:
            total += (s.end_at - s.start_at).total_seconds()
    return total


def summarize(session: Session) -> SessionSummary:
    animal_summaries: list[AnimalSummary] = []

    for name, animal in session.animals.items():
        stages: list[StageSummary] = []
        for stage_name, stage_state in animal.stages.items():
            stages.append(
                StageSummary(
                    name=stage_name,
                    trials=stage_state.stage_trial_id,
                    initial_level=stage_state.initial_level,
                    final_level=stage_state.level,
                )
            )

        animal_summaries.append(
            AnimalSummary(
                name=name,
                rfid_tags=animal.config.rfid_tags,
                total_trials=animal.trial_id,
                animal_sessions=len(animal.animal_sessions),
                total_duration_seconds=_calc_animal_duration(animal.animal_sessions),
                stages=stages,
            )
        )

    duration = 0.0
    if session.start_at and session.end_at:
        duration = (session.end_at - session.start_at).total_seconds()

    return SessionSummary(
        session_id=session.session_id,
        start_at=session.start_at,
        end_at=session.end_at,
        duration_seconds=duration,
        experimenter=session.experimenter,
        reward_type=session.reward_type.value,
        total_animals=len(session.animals),
        note=session.note,
        animals=animal_summaries,
    )


def session_overview(summary: SessionSummary) -> str:
    lines = [
        f"Session #{summary.session_id}",
        f"Start: {_format_timestamp(summary.start_at)}",
        f"End: {_format_timestamp(summary.end_at)}",
        f"Duration: {_format_duration(summary.duration_seconds)}",
        f"Experimenter: {summary.experimenter}",
        f"Reward type: {summary.reward_type}",
    ]
    if summary.note:
        lines.append(f"Note: {summary.note}")

    lines += ["", f"Animals ({summary.total_animals})"]
    for animal in summary.animals:
        lines.append(
            f"- {animal.name} ({', '.join(animal.rfid_tags) or 'no RFID'}): {animal.total_trials} trials, "
            f"{animal.animal_sessions} sessions, "
            f"{_format_duration(animal.total_duration_seconds)}"
        )
        lines += [
            f"  {stage.name}: {stage.trials} trials, {_format_level(stage)}"
            for stage in animal.stages
        ]
    return "\n".join(lines)


def build_session_report(
    session: Session,
    stage_post_processors: Mapping[str, StagePostProcessor],
) -> str:
    """Build the plain-text session report from the summary and stage sections."""
    sections = [session_overview(summarize(session))]

    if session.data_root is not None:
        for stage_name, paths_by_animal in session.stage_data_paths.items():
            post_processor = stage_post_processors.get(stage_name)
            if post_processor is None:
                logger.warning("skipping stage without post-processor: {}", stage_name)
                continue

            stage_paths = {
                animal: session.data_root / path
                for animal, path in paths_by_animal.items()
            }
            sections.append(post_processor.process(session, stage_paths).text)

    return "\n\n".join(sections)


def send_session_report(
    session: Session,
    stage_post_processors: Mapping[str, StagePostProcessor],
) -> None:
    """Build the completed session report and notify the device's subscribers."""
    if not session.send_email:
        return

    try:
        notify(
            f"{session.mxbi_config.mxbi_id} Daily Report",
            build_session_report(session, stage_post_processors),
        )
        logger.info("session report sent: session_id={}", session.session_id)
    except Exception:
        logger.exception("failed to send session report")
        raise
