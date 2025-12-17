import sys
from datetime import datetime
from pathlib import Path
from tkinter import Tk, filedialog
from tkinter.ttk import Button, Frame, Label, Entry

from mxbi.config import session_config, session_options
from mxbi.models.animal import AnimalConfig
from mxbi.models.detector import DetectorEnum
from mxbi.models.reward import RewardEnum
from mxbi.models.session import ScreenTypeEnum, SessionConfig
from mxbi.peripheral.pumps.pump_factory import PumpEnum
from mxbi.ui.components.animal_card import AnimalCard
from mxbi.ui.components.fileds.labeled_combobox import (
    LabeledCombobox,
    create_cobmbo,
)
from mxbi.ui.components.fileds.labeled_textbox import create_textbox
from mxbi.utils.detect_platform import PlatformEnum


class LaunchPanel:
    """Tkinter based configuration launcher for MXBI sessions."""

    def __init__(self) -> None:
        self._root = Tk()
        self._root.title("mxbi")
        self._init_ui()
        self._root.mainloop()

    def _init_ui(self) -> None:
        self._frame = Frame(self._root)
        self._frame.pack()

        self._init_general_ui()
        self._init_detector_ui()
        self._init_animals_ui()
        self._init_animals_buttons_ui()
        self._init_buttons_ui()

        self._bind_events()

    def _init_general_ui(self) -> None:
        frame_general = self._create_section_frame("General")

        self.combo_experimenter = self._pack_combo(
            frame_general,
            "Experimenter: ",
            session_options.value.experimenter,
            session_config.value.experimenter,
        )

        self.combo_xbi = self._pack_combo(
            frame_general,
            "XBI: ",
            session_options.value.xbi_id,
            session_config.value.xbi_id,
        )

        self.combo_reward = self._pack_combo(
            frame_general,
            "Reward: ",
            list(session_options.value.reward_type),
            session_config.value.reward_type,
        )

        self.combo_pump = self._pack_combo(
            frame_general,
            "Pump: ",
            list(session_options.value.pump_type),
            session_config.value.pump_type,
        )

        self.combo_platform = self._pack_combo(
            frame_general,
            "Platform: ",
            list(session_options.value.platform),
            session_config.value.platform,
        )

        screen_options = [screen.value for screen in session_options.value.screen_type]
        default_screen = session_config.value.screen_type.name.value
        if default_screen not in screen_options:
            screen_options.insert(0, default_screen)

        self.combo_screen = self._pack_combo(
            frame_general,
            "Screen: ",
            screen_options,
            default_screen,
        )

        self.entry_comments = create_textbox(frame_general, "Comments: ", height=4)
        self.entry_comments.pack(fill="x")

    def _init_detector_ui(self) -> None:
        frame_detector = self._create_section_frame("Detector")

        detector_options = [
            detector.value for detector in session_options.value.detecotr
        ]
        default_detector = session_config.value.detector.value
        if default_detector not in detector_options:
            detector_options.insert(0, default_detector)

        self.combo_detector = self._pack_combo(
            frame_detector,
            "Detector: ",
            detector_options,
            default_detector,
        )

        available_ports = self._available_detector_ports()
        default_port = session_config.value.detector_port or ""
        if default_port and default_port not in available_ports:
            available_ports.insert(0, default_port)
        if "" not in available_ports:
            available_ports.insert(0, "")

        # Allow typing a custom device path when auto-detection fails.
        self.combo_detector_port = self._pack_combo(
            frame_detector,
            "Port: ",
            available_ports,
            default_port,
            state="normal",
        )

        baudrate_options = [
            str(baudrate) for baudrate in session_options.value.detector_baudrates
        ]
        if not baudrate_options:
            baudrate_options = [""]

        default_baudrate = (
            str(session_config.value.detector_baudrate)
            if session_config.value.detector_baudrate is not None
            else baudrate_options[0]
        )

        self.combo_detector_baudrate = self._pack_combo(
            frame_detector,
            "Baudrate: ",
            baudrate_options,
            default_baudrate,
        )

        self.text_detector_interval = create_textbox(
            frame_detector, "Interval: ", height=1
        )
        self.text_detector_interval.insert(str(session_config.value.detector_interval))
        self.text_detector_interval.pack(fill="x")

    def _init_animals_ui(self) -> None:
        self.frame_animals = Frame(self._frame)
        self.frame_animals.pack(fill="x")
        self.frame_animals.columnconfigure(0, weight=1)
        self.frame_animals.columnconfigure(1, weight=1)

        self._animal_cards: list[AnimalCard] = []
        for index, animal in enumerate(session_config.value.animals.values()):
            animal_card = AnimalCard(
                self.frame_animals, session_options.value.animal, animal, index
            )
            animal_card.grid(
                row=index // 2, column=index % 2, padx=2, pady=2, sticky="ew"
            )
            self._animal_cards.append(animal_card)

    def _init_animals_buttons_ui(self) -> None:
        frame_animals_buttons = Frame(self._frame)
        frame_animals_buttons.pack(fill="x")
        frame_animals_buttons.columnconfigure(0, weight=1)

        button_add_animal = Button(
            frame_animals_buttons, text="Add animal", command=self._add_animal
        )
        button_add_animal.grid(row=0, column=0, padx=2, pady=2, sticky="w")

        button_remove_animal = Button(
            frame_animals_buttons, text="Remove animal", command=self._remove_animal
        )
        button_remove_animal.grid(row=0, column=1, padx=2, pady=2, sticky="e")

    def _init_buttons_ui(self) -> None:
        frame_button = Frame(self._frame)
        frame_button.pack(fill="x")
        frame_button.columnconfigure(0, weight=1)

        button_cancel = Button(frame_button, text="Cancel", command=sys.exit)
        button_cancel.grid(row=0, column=0, padx=2, pady=2, sticky="w")

        button_start = Button(frame_button, text="Start", command=self.save)
        button_start.grid(row=0, column=1, padx=2, pady=2, sticky="e")

    def _add_animal(self) -> None:
        if self.frame_animals is None:
            return

        index = len(self._animal_cards)
        new_animal = AnimalConfig()
        animal_card = AnimalCard(
            self.frame_animals, session_options.value.animal, new_animal, index
        )
        animal_card.grid(row=index // 2, column=index % 2, padx=2, pady=2, sticky="ew")
        self._animal_cards.append(animal_card)

    def _remove_animal(self) -> None:
        if not self._animal_cards:
            return
        animal_card = self._animal_cards.pop()
        animal_card.destroy()

    def _bind_events(self) -> None:
        # Auto-start provides a safety net if the panel is left unattended.
        self._root.after(60000, self._auto_start)
        self._root.protocol("WM_DELETE_WINDOW", sys.exit)

    def _auto_start(self):
        """Kick off a session automatically when the operator does not interact in time."""
        current_time = datetime.now().strftime("%Y%m%d-%H-%M-%S-%f")[:-3]
        timezone = datetime.now().astimezone().tzinfo

        config = self._build_session_config(
            experimenter="auto",
            comments=f"Auto task, start time: {current_time} (UTC{timezone})",
        )
        self._save_and_close(config)

    def save(self) -> None:
        config = self._build_session_config(
            experimenter=self.combo_experimenter.get(),
            comments=self.entry_comments.get(),
        )
        self._save_and_close(config)

    def _build_session_config(self, experimenter: str, comments: str) -> SessionConfig:
        return SessionConfig(
            experimenter=experimenter,
            xbi_id=self.combo_xbi.get(),
            reward_type=RewardEnum(self.combo_reward.get()),
            pump_type=PumpEnum(self.combo_pump.get()),
            platform=PlatformEnum(self.combo_platform.get()),
            detector=DetectorEnum(self.combo_detector.get()),
            detector_port=self._selected_detector_port(),
            detector_baudrate=self._selected_detector_baudrate(),
            detector_interval=self._selected_detector_interval(),
            screen_type=self._selected_screen_type(),
            comments=comments,
            animals=self._collect_animals(),
        )

    def _collect_animals(self) -> dict[str, AnimalConfig]:
        return {
            animal_card.data.name: animal_card.data
            for animal_card in self._animal_cards
        }

    def _selected_detector_port(self) -> str | None:
        value = self.combo_detector_port.get().strip()
        return value or None

    def _selected_detector_baudrate(self) -> int | None:
        value = self.combo_detector_baudrate.get().strip()
        return int(value) if value else None

    def _selected_detector_interval(self) -> float | None:
        value = self.text_detector_interval.get().strip()
        if value != "None":
            return float(value) if value else None

    def _selected_screen_type(self):
        screen_key = ScreenTypeEnum(self.combo_screen.get())
        return session_options.value.screen_type[screen_key]

    @staticmethod
    def _normalize_path(value: str) -> str | None:
        value = value.strip()
        return value or None

    def _save_and_close(self, config: SessionConfig) -> None:
        session_config.save(config)
        self._root.destroy()

    def _available_detector_ports(self) -> list[str]:
        """Return serial device paths detected on the host."""
        try:
            from serial.tools import list_ports
        except ModuleNotFoundError:
            return []

        try:
            ports = [port.device for port in list_ports.comports()]
        except Exception:
            ports = []

        return sorted(ports)

    def _create_section_frame(self, title: str) -> Frame:
        """Create a vertically stacked frame with a section heading."""
        frame = Frame(self._frame)
        frame.pack(fill="x")
        frame.columnconfigure(0, weight=1)
        Label(frame, text=title).pack()
        return frame

    def _pack_combo(
        self,
        parent: Frame,
        label: str,
        values: list,
        default_value,
        state: str = "readonly",
    ) -> LabeledCombobox:
        combo = create_cobmbo(parent, label, values, default_value, state=state)
        combo.pack(fill="x", expand=True)
        return combo


if __name__ == "__main__":
    panel = LaunchPanel()
