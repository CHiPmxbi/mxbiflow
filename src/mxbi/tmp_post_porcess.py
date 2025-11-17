import json
from pathlib import Path
import matplotlib.pyplot as plt
from io import BytesIO

from mxbi.tasks.default.initial_habituation_training.tasks.stay_to_reward.stay_to_reward_models import (
    TrialData,
)
from mxbi.tmp_email import send_email, EmailAttachment
from datetime import datetime


def load_data(path: Path) -> list:
    with open(path, "r", encoding="utf-8") as f:
        data = []
        for line in f:
            if line.strip():
                obj = json.loads(line)
                data.append(obj)

    return data


def parse_data(data: list) -> list[TrialData]:
    return [TrialData.model_validate(obj) for obj in data]


class HabituationTrainingStagePostProcess:
    def __init__(self, paths: list[Path]) -> None:
        self._data = [parse_data(load_data(path)) for path in paths]
        self.animals = [animal[0].animal for animal in self._data]
        self.stay_durations = [
            sum(trial.stay_duration for trial in item) for item in self._data
        ]
        summary = self._plot_animals_stay_duaration()

        attachment = EmailAttachment(
            filename="habituation_training_summary.png",
            content=summary,
        )

        date = datetime.now().strftime("%Y-%m-%d")
        animals_html = "".join(f"<li>{a}</li>" for a in self.animals)

        content = f"""
        <h2>Habituation Training Stage Summary - {date}</h2>
        <ul>
            <li>Total Animals: {len(self._data)}</li>
            {animals_html}
        </ul>
        """

        send_email(
            subject=f"Habituation Training Stage Summary - {date}",
            body=content,
            attachments=[attachment],
        )

    def _plot_animals_stay_duaration(self) -> bytes:
        fig, ax = plt.subplots()

        ax.bar(self.animals, self.stay_durations)
        ax.set_xlabel("Animal")
        ax.set_ylabel("Total Stay Duration (s)")
        ax.set_title("Total Stay Duration per Animal in Habituation Training Stage")

        buf = BytesIO()
        plt.savefig(buf, format="png", dpi=300)
        buf.seek(0)

        img_bytes = buf.getvalue()
        return img_bytes
