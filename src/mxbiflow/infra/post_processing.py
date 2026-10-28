from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from io import BytesIO
from pathlib import Path

from loguru import logger
from matplotlib.figure import Figure
from pydantic import BaseModel
from pymotego import Block, Client, Heading, Image, KeyValue, Paragraph, Stats, Table

from ..models.animal import AnimalSessionState
from ..models.session import Session
from .camera_recording import TrialMark


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


#: Width in inches of a report figure: the email shows images 560 px wide.
FIGURE_WIDTH_IN = 5.6


def report_figure(height_in: float = 3.5) -> Figure:
    """A blank figure that reads well at the email's 560 px image width."""
    return Figure(figsize=(FIGURE_WIDTH_IN, height_in), layout="constrained")


def figure_png(figure: Figure, *, dpi: int = 200) -> bytes:
    """Return ``figure`` as PNG bytes, at twice the 560 px width for sharp screens.

    Build figures with :func:`report_figure` (a ``matplotlib.figure.Figure`` rather than
    pyplot, so no GUI backend is involved and nothing has to be closed).
    """
    buffer = BytesIO()
    figure.savefig(buffer, format="png", dpi=dpi, bbox_inches="tight")
    return buffer.getvalue()


class StagePostProcessor(ABC):
    """Builds one stage's section of the daily report.

    mxbiflow writes the fixed part (title, session stats, animals, session details);
    a stage's section follows this convention so every report reads the same:

    - a ``Heading`` with the stage name;
    - one line of key numbers (trials, accuracy, median reaction time, ...) as a
      ``Stats`` block of at most six items, or a ``KeyValue`` block;
    - one or more figures, each an ``Image`` block with a caption; draw them on
      :func:`report_figure` and encode them with :func:`figure_png`.

    Tables of per-animal details may follow. Round numbers yourself: blocks show values
    as given.
    """

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
        return f"{stage.initial_level} (no change)"
    return f"{stage.initial_level} -> {stage.final_level} ({change:+d})"


def _format_levels(stages: Sequence[StageSummary]) -> str:
    if len(stages) == 1:
        return _format_level(stages[0])
    return "; ".join(f"{stage.name} {_format_level(stage)}" for stage in stages)


def accuracy(trials: Sequence[TrialMark], animal: str | None = None) -> float | None:
    """Correct among the judged trials (of ``animal``); None without judged trials.

    Trials are judged by the ``correct`` the stage passes to ``publish_trial``, so
    accuracy needs no stage-specific data.
    """
    judged = [
        t.correct
        for t in trials
        if t.correct is not None and (animal is None or t.animal == animal)
    ]
    return sum(judged) / len(judged) if judged else None


def _format_accuracy(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.0%}"


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


def session_overview(
    summary: SessionSummary, trials: Sequence[TrialMark] = (), task: str = ""
) -> list[Block]:
    """The report's fixed part: subtitle, stats, animals and session details."""
    date = summary.start_at.astimezone().date().isoformat() if summary.start_at else ""
    subtitle = " · ".join(
        part for part in (f"Session #{summary.session_id}", date, task) if part
    )
    blocks: list[Block] = [
        Paragraph(subtitle),
        Stats(
            [
                ("Duration", _format_duration(summary.duration_seconds)),
                ("Animals", summary.total_animals),
                ("Trials", sum(a.total_trials for a in summary.animals)),
                ("Accuracy", _format_accuracy(accuracy(trials))),
            ]
        ),
    ]
    if summary.animals:
        blocks.append(
            Table(
                ["Animal", "Trials", "Accuracy", "Level change"],
                [
                    [
                        animal.name,
                        animal.total_trials,
                        _format_accuracy(accuracy(trials, animal.name)),
                        _format_levels(animal.stages),
                    ]
                    for animal in summary.animals
                ],
            )
        )
    details = [
        ("Start", _format_timestamp(summary.start_at)),
        ("End", _format_timestamp(summary.end_at)),
        ("Experimenter", summary.experimenter),
        ("Reward type", summary.reward_type),
    ]
    if summary.note:
        details.append(("Note", summary.note))
    blocks += [Heading("Session details"), KeyValue(details)]
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
    trials: Sequence[TrialMark] = (),
    task: str = "",
) -> SessionReport:
    """Build the daily report: the fixed part, then each stage's section.

    ``trials`` are the run's published trials, for accuracy; ``task`` names the
    experiment in the subtitle.
    """
    summary = summarize(session)
    blocks = session_overview(summary, trials, task)
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

    total = sum(animal.total_trials for animal in summary.animals)
    return SessionReport(
        title=f"{session.device_name} daily report",
        summary=f"Session #{summary.session_id}: {summary.total_animals} animals, "
        f"{total} trials, {_format_duration(summary.duration_seconds)}",
        blocks=blocks,
        images=images,
    )


def send_session_report(
    session: Session,
    stage_post_processors: Mapping[str, StagePostProcessor],
) -> None:
    """Send the completed session report when the session config asks for it."""
    if session.send_email:
        try:
            report = build_session_report(session, stage_post_processors)
        except Exception:
            logger.exception("failed to build session report")
            raise
        deliver_session_report(report)


def deliver_session_report(report: SessionReport) -> str:
    """Send ``report`` to the device's subscribers and return its URL."""
    try:
        with Client() as client:
            receipt = client.report(
                report.title, report.blocks, report.images, summary=report.summary
            )
        logger.info("session report sent: {} url={}", report.title, receipt.url)
        return receipt.url
    except Exception:
        logger.exception("failed to send session report")
        raise
