from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Self, TypedDict

from jinja2 import Environment, FileSystemLoader, select_autoescape
from loguru import logger
from pydantic import BaseModel
from pymotego import EmailClient, EmailEmbed

from ..core.path import get_runtime_state_path
from ..models.animal import AnimalSessionState
from ..models.session import RuntimeStateStore, Session


class StageSummary(BaseModel):
    name: str
    trials: int
    initial_level: int
    final_level: int


class AnimalSummary(BaseModel):
    name: str
    rfid_id: str
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


class ReportImage(TypedDict):
    cid: str
    alt: str


@dataclass(frozen=True)
class PostProcessingResult:
    html: str
    embeds: tuple[EmailEmbed, ...] = ()


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


def _calc_animal_duration(sessions: Sequence[AnimalSessionState]) -> float:
    total = 0.0
    for s in sessions:
        if s.start_at and s.end_at:
            total += (s.end_at - s.start_at).total_seconds()
    return total


_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _get_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "xml"]),
    )


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
                rfid_id=animal.config.rfid_id,
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
    env = _get_jinja_env()
    template = env.get_template("session_overview.html")

    context: dict[str, object] = {
        "session_id": summary.session_id,
        "session_date": (
            summary.start_at.astimezone().strftime("%Y-%m-%d")
            if summary.start_at
            else "N/A"
        ),
        "start_time": _format_timestamp(summary.start_at),
        "end_time": _format_timestamp(summary.end_at),
        "duration": _format_duration(summary.duration_seconds),
        "reward_type": summary.reward_type,
        "total_animals": summary.total_animals,
        "animals": [
            {
                **a.model_dump(),
                "duration": _format_duration(a.total_duration_seconds),
            }
            for a in summary.animals
        ],
    }

    return template.render(**context)


def render_image_section_report(section_title: str, images: list[ReportImage]) -> str:
    env = _get_jinja_env()
    template = env.get_template("section_report.html")
    return template.render(section_title=section_title, images=images)


class HtmlComposer:
    def __init__(self, title: str, date: str) -> None:
        self._title = title
        self._date = date
        self._sections: list[str] = []
        self._env = _get_jinja_env()

    def add_section(self, html: str) -> Self:
        self._sections.append(html)
        return self

    @property
    def html(self) -> str:
        template = self._env.get_template("page_layout.html")
        return template.render(
            title=self._title,
            date=self._date,
            sections=self._sections,
        )

    def save(self, path: Path) -> None:
        path.write_text(self.html, encoding="utf-8")


def build_session_report(
    session: Session,
    stage_post_processors: Mapping[str, StagePostProcessor],
) -> PostProcessingResult:
    summary = summarize(session)
    date = (
        summary.start_at.astimezone(UTC).strftime("%Y-%m-%d")
        if summary.start_at is not None
        else "N/A"
    )
    composer = HtmlComposer(title=f"Session #{summary.session_id}", date=date)
    composer.add_section(session_overview(summary))

    embeds: list[EmailEmbed] = []
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
            result = post_processor.process(session, stage_paths)
            composer.add_section(result.html)
            embeds.extend(result.embeds)

    return PostProcessingResult(html=composer.html, embeds=tuple(embeds))


def send_session_report(
    session: Session,
    stage_post_processors: Mapping[str, StagePostProcessor],
) -> None:
    """Build and send the completed session report."""
    if not session.send_email:
        return

    try:
        report = build_session_report(session, stage_post_processors)
        runtime_store = RuntimeStateStore(get_runtime_state_path())
        previous_message_id = runtime_store.email_message_id
        with EmailClient() as client:
            result = client.send(
                subject=f"{session.mxbi_config.mxbi_id} Daily Report",
                html_body=report.html,
                embeds=list(report.embeds),
                in_reply_to=previous_message_id or None,
            )
        runtime_store.save_email_message_id(result.message_id)
        logger.info("session report sent: session_id={}", session.session_id)
    except Exception:
        logger.exception("failed to send session report")
        raise
