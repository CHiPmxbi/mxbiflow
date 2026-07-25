from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Self, TypedDict

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel

from ..core.context import get_mxbiflow
from ..models.animal import AnimalSessionState


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
    reward_type: str
    total_animals: int
    animals: list[AnimalSummary]


class ReportImage(TypedDict):
    cid: str
    alt: str


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


def summarize() -> SessionSummary:
    session = get_mxbiflow().session
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
                rfid_id=animal.rfid_id,
                total_trials=animal.trial_id,
                animal_sessions=len(animal.sessions),
                total_duration_seconds=_calc_animal_duration(animal.sessions),
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
        reward_type=session.reward_type.value,
        total_animals=len(session.animals),
        animals=animal_summaries,
    )


def session_overview() -> str:
    summary = summarize()
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
