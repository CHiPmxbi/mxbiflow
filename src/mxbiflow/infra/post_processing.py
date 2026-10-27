from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from io import BytesIO
from pathlib import Path

from loguru import logger
from matplotlib.figure import Figure
from pydantic import BaseModel
from pymotego import Block, Client, Heading, Image, KeyValue, Table

from ..models.animal import AnimalSessionState
from ..models.session import Session


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
    """One stage's section of the daily report.

    ``blocks`` are pymoteGO report blocks (cogmote renders them); ``figures`` are PNG images
    keyed by the names ``Image`` blocks use. Names only need to be unique within the stage.
    """

    blocks: Sequence[Block]
    figures: Mapping[str, bytes] = field(default_factory=dict[str, bytes])


def figure_png(figure: Figure, *, dpi: int = 100) -> bytes:
    """Return ``figure`` as PNG bytes.

    Build figures with ``matplotlib.figure.Figure`` rather than pyplot, so no GUI backend
    is involved and nothing has to be closed.
    """
    buffer = BytesIO()
    figure.savefig(buffer, format="png", dpi=dpi, bbox_inches="tight")
    return buffer.getvalue()


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


def session_overview(summary: SessionSummary) -> list[Block]:
    """The overview section: session metadata, animals and their stages."""
    details = [
        ("Start", _format_timestamp(summary.start_at)),
        ("End", _format_timestamp(summary.end_at)),
        ("Duration", _format_duration(summary.duration_seconds)),
        ("Experimenter", summary.experimenter),
        ("Reward type", summary.reward_type),
    ]
    if summary.note:
        details.append(("Note", summary.note))
    blocks: list[Block] = [Heading(f"Session #{summary.session_id}"), KeyValue(details)]
    if not summary.animals:
        return blocks
    blocks.append(
        Table(
            ["Animal", "RFID", "Trials", "Sessions", "Duration"],
            [
                [
                    animal.name,
                    ", ".join(animal.rfid_tags) or "no RFID",
                    animal.total_trials,
                    animal.animal_sessions,
                    _format_duration(animal.total_duration_seconds),
                ]
                for animal in summary.animals
            ],
            caption=f"Animals ({summary.total_animals})",
        )
    )
    stage_rows = [
        [animal.name, stage.name, stage.trials, _format_level(stage)]
        for animal in summary.animals
        for stage in animal.stages
    ]
    if stage_rows:
        blocks.append(Table(["Animal", "Stage", "Trials", "Level"], stage_rows))
    return blocks


@dataclass(frozen=True)
class SessionReport:
    """The daily report as pymoteGO ``Client.report`` takes it."""

    title: str
    summary: str
    blocks: list[Block]
    images: dict[str, bytes]


def _stage_section(index: int, result: PostProcessingResult) -> PostProcessingResult:
    """Prefix the stage's image names so stages may reuse them."""

    def name(image: str) -> str:
        return f"s{index}-{image}"[:64]

    blocks = [
        replace(block, image=name(block.image)) if isinstance(block, Image) else block
        for block in result.blocks
    ]
    return PostProcessingResult(
        blocks, {name(image): png for image, png in result.figures.items()}
    )


def build_session_report(
    session: Session,
    stage_post_processors: Mapping[str, StagePostProcessor],
) -> SessionReport:
    """Build the daily report from the summary and the stage sections."""
    summary = summarize(session)
    blocks = session_overview(summary)
    images: dict[str, bytes] = {}

    if session.data_root is not None:
        for index, (stage_name, paths_by_animal) in enumerate(
            session.stage_data_paths.items()
        ):
            post_processor = stage_post_processors.get(stage_name)
            if post_processor is None:
                logger.warning("skipping stage without post-processor: {}", stage_name)
                continue

            stage_paths = {
                animal: session.data_root / path
                for animal, path in paths_by_animal.items()
            }
            section = _stage_section(
                index, post_processor.process(session, stage_paths)
            )
            blocks.extend(section.blocks)
            images.update(section.figures)

    trials = sum(animal.total_trials for animal in summary.animals)
    return SessionReport(
        title=f"{session.mxbi_config.mxbi_id} Daily Report",
        summary=f"Session #{summary.session_id}: {summary.total_animals} animals, "
        f"{trials} trials, {_format_duration(summary.duration_seconds)}",
        blocks=blocks,
        images=images,
    )


def send_session_report(
    session: Session,
    stage_post_processors: Mapping[str, StagePostProcessor],
) -> None:
    """Send the completed session report when the session config asks for it."""
    if session.send_email:
        deliver_session_report(session, stage_post_processors)


def deliver_session_report(
    session: Session,
    stage_post_processors: Mapping[str, StagePostProcessor],
) -> str:
    """Build the session report, send it to the device's subscribers and return its URL."""
    try:
        report = build_session_report(session, stage_post_processors)
        with Client() as client:
            receipt = client.report(
                report.title, report.blocks, report.images, summary=report.summary
            )
        logger.info(
            "session report sent: session_id={} url={}", session.session_id, receipt.url
        )
        return receipt.url
    except Exception:
        logger.exception("failed to send session report")
        raise
