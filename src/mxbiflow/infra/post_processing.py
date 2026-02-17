from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel

from ..core.context import get_mxbiflow


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
    start_at: float
    end_at: float
    duration_seconds: float
    reward_type: str
    total_animals: int
    animals: list[AnimalSummary]


def _format_timestamp(ts: float) -> str:
    if ts == 0:
        return "N/A"
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


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


def _calc_animal_duration(sessions: list) -> float:
    total = 0.0
    for s in sessions:
        if s.start_at and s.end_at:
            total += s.end_at - s.start_at
    return total


class PostProcessor:
    def __init__(self) -> None:
        self._mxbiflow = get_mxbiflow()
        self._template_dir = Path(__file__).parent / "templates"
        self._env = Environment(
            loader=FileSystemLoader(self._template_dir),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def summarize(self) -> SessionSummary:
        session = self._mxbiflow.session
        animal_summaries: list[AnimalSummary] = []

        for name, animal in session.animals.items():
            stages: list[StageSummary] = []
            for stage_name, stage_state in animal._stages.items():
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
                    animal_sessions=len(animal._sessions),
                    total_duration_seconds=_calc_animal_duration(animal._sessions),
                    stages=stages,
                )
            )

        duration = session.end_at - session.start_at if session.end_at > 0 else 0

        return SessionSummary(
            session_id=session.session_id,
            start_at=session.start_at,
            end_at=session.end_at,
            duration_seconds=duration,
            reward_type=session.reward_type.value,
            total_animals=len(session.animals),
            animals=animal_summaries,
        )

    @property
    def html(self) -> str:
        summary = self.summarize()
        template = self._env.get_template("session_summary.html")

        return template.render(
            session_id=summary.session_id,
            session_date=datetime.fromtimestamp(
                summary.start_at, tz=timezone.utc
            ).strftime("%Y-%m-%d"),
            start_time=_format_timestamp(summary.start_at),
            end_time=_format_timestamp(summary.end_at),
            duration=_format_duration(summary.duration_seconds),
            reward_type=summary.reward_type,
            total_animals=summary.total_animals,
            animals=[
                {
                    **a.model_dump(),
                    "duration": _format_duration(a.total_duration_seconds),
                }
                for a in summary.animals
            ],
        )

    def save(self) -> None:
        output_path = self._mxbiflow.data_dir / "session_summary.html"
        output_path.write_text(self.html, encoding="utf-8")
