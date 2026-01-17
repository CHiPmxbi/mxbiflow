import sys
from datetime import datetime
from pathlib import Path
from tkinter import END, Listbox, Tk, filedialog
from tkinter.ttk import Button, Frame, Label, Notebook, Entry

from pydantic import ValidationError

from mxbi.config import session_config, session_options
from mxbi.models.animal import AnimalConfig
from mxbi.models.detector import DetectorEnum
from mxbi.models.reward import RewardEnum
from mxbi.models.session import ScreenTypeEnum, SessionConfig
from mxbi.models.task import TaskEnum
from mxbi.peripheral.pumps.pump_factory import PumpEnum
from mxbi.tasks.cross_modal.bundle_dir import BundleValidationError, CrossModalBundleDir
from mxbi.tasks.cross_modal.config import (
    CrossModalConfig,
    load_cross_modal_config,
    save_cross_modal_config,
)
from mxbi.ui.components.animal_card import AnimalCard
from mxbi.ui.components.fileds.labeled_combobox import (
    LabeledCombobox,
    create_cobmbo,
)
from mxbi.ui.components.fileds.labeled_entey import LabeledEntry, create_entry
from mxbi.ui.components.fileds.labeled_scale import LabeledScale
from mxbi.ui.components.fileds.labeled_textbox import create_textbox
from mxbi.utils.detect_platform import PlatformEnum


class LaunchPanel:
    """Tkinter based configuration launcher for MXBI sessions."""

    def __init__(self) -> None:
        self._root = Tk()
        self._root.title("mxbi")

        try:
            self._cross_modal_config = load_cross_modal_config()
        except FileNotFoundError:
            self._cross_modal_config = CrossModalConfig()

        self._cross_modal_bundle: CrossModalBundleDir | None = None

        self._init_ui()
        self._root.mainloop()

    def _init_ui(self) -> None:
        self._notebook = Notebook(self._root)
        self._notebook.pack(fill="both", expand=True)

        self._frame_session = Frame(self._notebook)
        self._frame_cross_modal = Frame(self._notebook)

        self._notebook.add(self._frame_session, text="Session")
        self._notebook.add(self._frame_cross_modal, text="Cross-modal")

        self._frame = self._frame_session

        self._init_general_ui()
        self._init_detector_ui()
        self._init_animals_ui()
        self._init_animals_buttons_ui()
        self._init_buttons_ui()

        self._init_cross_modal_ui()

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

    def _init_cross_modal_ui(self) -> None:
        self._frame = self._frame_cross_modal

        frame_bundle = self._create_section_frame("Dataset bundle")

        bundle_row = Frame(frame_bundle)
        bundle_row.pack(fill="x", expand=True)
        bundle_row.columnconfigure(1, weight=1)

        Label(bundle_row, text="Bundle dir:").grid(row=0, column=0, padx=(10, 0), pady=2, sticky="w")
        self.entry_cross_modal_bundle_dir = Entry(bundle_row)
        self.entry_cross_modal_bundle_dir.grid(row=0, column=1, padx=(0, 10), pady=2, sticky="ew")

        browse_btn = Button(
            bundle_row,
            text="Browse…",
            command=self._browse_cross_modal_bundle_dir,
        )
        browse_btn.grid(row=0, column=2, padx=(0, 10), pady=2, sticky="e")

        frame_subjects = self._create_section_frame("Subjects")
        self.listbox_cross_modal_subjects = Listbox(frame_subjects, selectmode="extended", height=6, exportselection=False)
        self.listbox_cross_modal_subjects.pack(fill="x", expand=True, padx=10, pady=2)

        frame_validation = self._create_section_frame("Validation")
        self.text_cross_modal_validation = create_textbox(frame_validation, "Errors: ", height=6)
        self.text_cross_modal_validation.pack(fill="x")

        frame_visual = self._create_section_frame("Visual")

        self.scale_cross_modal_image_scale = LabeledScale(
            frame_visual,
            "Image size: ",
            from_value=0.2,
            to_value=0.8,
            default_value=self._cross_modal_config.visual.image_scale,
            value_format="{:.2f}",
        )
        self.scale_cross_modal_image_scale.pack(fill="x", expand=True)

        frame_audio = self._create_section_frame("Audio")

        self.scale_cross_modal_master_volume = LabeledScale(
            frame_audio,
            "Master volume: ",
            from_value=0,
            to_value=100,
            default_value=float(self._cross_modal_config.audio.master_volume),
            value_format="{:.0f}",
        )
        self.scale_cross_modal_master_volume.pack(fill="x", expand=True)

        self.scale_cross_modal_digital_volume = LabeledScale(
            frame_audio,
            "Digital volume: ",
            from_value=0,
            to_value=100,
            default_value=float(self._cross_modal_config.audio.digital_volume),
            value_format="{:.0f}",
        )
        self.scale_cross_modal_digital_volume.pack(fill="x", expand=True)

        self.scale_cross_modal_gain = LabeledScale(
            frame_audio,
            "Gain: ",
            from_value=0.0,
            to_value=2.0,
            default_value=self._cross_modal_config.audio.gain,
            value_format="{:.2f}",
        )
        self.scale_cross_modal_gain.pack(fill="x", expand=True)

        frame_timing = self._create_section_frame("Timing")

        self.entry_cross_modal_trial_timeout_sec: LabeledEntry = create_entry(
            frame_timing,
            "Trial timeout (s): ",
            self._format_seconds(self._cross_modal_config.timing.trial_timeout_ms),
        )
        self.entry_cross_modal_trial_timeout_sec.pack(fill="x", expand=True)

        frame_policy = self._create_section_frame("WAV sample rate")

        self.combo_cross_modal_wav_policy = self._pack_combo(
            frame_policy,
            "Policy: ",
            ["resample", "error"],
            self._cross_modal_config.audio.wav_rate_policy,
        )

        self._frame = self._frame_session

    def _browse_cross_modal_bundle_dir(self) -> None:
        path = filedialog.askdirectory(title="Select cross-modal dataset bundle directory")
        if not path:
            return
        self.entry_cross_modal_bundle_dir.delete(0, "end")
        self.entry_cross_modal_bundle_dir.insert(0, path)
        self._load_cross_modal_bundle()

    def _load_cross_modal_bundle(self) -> None:
        bundle_dir_str = self.entry_cross_modal_bundle_dir.get().strip()
        if not bundle_dir_str:
            self._cross_modal_bundle = None
            self._set_cross_modal_subjects([])
            self._set_cross_modal_errors("")
            return

        bundle_dir = Path(bundle_dir_str).expanduser().resolve()
        try:
            bundle = CrossModalBundleDir.from_dir_path(bundle_dir)
        except BundleValidationError as e:
            self._cross_modal_bundle = None
            self._set_cross_modal_subjects([])
            self._set_cross_modal_errors("\n".join(e.errors))
            return

        allowed_animals = set(session_options.value.animal.name)
        unknown_subjects = [s for s in bundle.subject_ids() if s not in allowed_animals]
        if unknown_subjects:
            self._cross_modal_bundle = None
            self._set_cross_modal_subjects(bundle.subject_ids())
            self._set_cross_modal_errors(
                "Bundle subjects are not present in options_session.json animal names:\n"
                + "\n".join(f"- {s}" for s in unknown_subjects)
            )
            return

        self._cross_modal_bundle = bundle
        self._set_cross_modal_subjects(bundle.subject_ids())
        self._set_cross_modal_errors("")

    def _set_cross_modal_subjects(self, subject_ids: list[str]) -> None:
        self.listbox_cross_modal_subjects.delete(0, END)
        for s in subject_ids:
            self.listbox_cross_modal_subjects.insert(END, s)
        if subject_ids:
            self.listbox_cross_modal_subjects.selection_set(0, END)

    def _set_cross_modal_errors(self, text: str) -> None:
        self.text_cross_modal_validation.set(text)

    def _selected_cross_modal_subjects(self) -> list[str]:
        selections = self.listbox_cross_modal_subjects.curselection()
        return [self.listbox_cross_modal_subjects.get(i) for i in selections]

    def _init_cross_modal_mode_animals(self) -> dict[str, AnimalConfig]:
        if self._cross_modal_bundle is None:
            return {}

        selected_subjects = self._selected_cross_modal_subjects()
        if not selected_subjects:
            return {}

        return {
            subject_id: AnimalConfig(name=subject_id, task=TaskEnum.CROSS_MODAL, level=0)
            for subject_id in selected_subjects
        }

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
        self._root.after(60000, self._auto_start)
        self._root.protocol("WM_DELETE_WINDOW", sys.exit)

    def _auto_start(self):
        current_time = datetime.now().strftime("%Y%m%d-%H-%M-%S-%f")[:-3]
        timezone = datetime.now().astimezone().tzinfo

        config = self._build_session_config(
            experimenter="auto",
            comments=f"Auto task, start time: {current_time} (UTC{timezone})",
        )
        self._save_and_close(config)

    def save(self) -> None:
        self._load_cross_modal_bundle()
        if self.entry_cross_modal_bundle_dir.get().strip():
            if self._cross_modal_bundle is None:
                self._notebook.select(self._frame_cross_modal)
                return

            selected_subjects = self._selected_cross_modal_subjects()
            if not selected_subjects:
                self._set_cross_modal_errors("Select at least one subject to start the cross-modal task.")
                self._notebook.select(self._frame_cross_modal)
                return

            try:
                self._cross_modal_bundle.validate_selected_subjects(selected_subjects)
            except BundleValidationError as e:
                self._set_cross_modal_errors("\n".join(e.errors))
                self._notebook.select(self._frame_cross_modal)
                return

        try:
            cross_modal_config = self._build_cross_modal_config()
        except (ValidationError, ValueError) as e:
            self._set_cross_modal_errors(str(e))
            self._notebook.select(self._frame_cross_modal)
            return

        config = self._build_session_config(
            experimenter=self.combo_experimenter.get(),
            comments=self.entry_comments.get(),
        )
        save_cross_modal_config(cross_modal_config)
        session_config.save(config)
        self._root.destroy()

    def _build_session_config(self, experimenter: str, comments: str) -> SessionConfig:
        bundle_dir = self.entry_cross_modal_bundle_dir.get().strip() or None
        animals_from_bundle = self._init_cross_modal_mode_animals() if bundle_dir else {}

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
            cross_modal_bundle_dir=bundle_dir,
            animals=animals_from_bundle if bundle_dir else self._collect_animals(),
        )

    def _build_cross_modal_config(self) -> CrossModalConfig:
        return CrossModalConfig(
            visual={
                "image_scale": self.scale_cross_modal_image_scale.get_float(),
            },
            audio={
                "master_volume": self.scale_cross_modal_master_volume.get_int(),
                "digital_volume": self.scale_cross_modal_digital_volume.get_int(),
                "gain": self.scale_cross_modal_gain.get_float(),
                "wav_rate_policy": self.combo_cross_modal_wav_policy.get(),
            },
            timing={
                "fixation_ms": self._cross_modal_config.timing.fixation_ms,
                "trial_timeout_ms": self._selected_cross_modal_trial_timeout_ms(),
            },
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

    def _save_and_close(self, config: SessionConfig) -> None:
        save_cross_modal_config(self._build_cross_modal_config())
        session_config.save(config)
        self._root.destroy()

    def _available_detector_ports(self) -> list[str]:
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

    @staticmethod
    def _format_seconds(milliseconds: int) -> str:
        seconds = milliseconds / 1000.0
        formatted = f"{seconds:.3f}".rstrip("0").rstrip(".")
        return formatted or "0"

    def _selected_cross_modal_trial_timeout_ms(self) -> int:
        raw = self.entry_cross_modal_trial_timeout_sec.get().strip()
        if not raw:
            raise ValueError("Trial timeout (s) is required.")

        normalized = raw.replace(",", ".")
        seconds = float(normalized)
        if seconds <= 0:
            raise ValueError("Trial timeout (s) must be > 0.")

        return int(round(seconds * 1000.0))


if __name__ == "__main__":
    panel = LaunchPanel()
