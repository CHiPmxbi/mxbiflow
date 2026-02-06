from pathlib import Path

from ..config_store import ConfigStore
from ..models.animal import Animal, StageState
from ..models.session import DailySessionIdStore, Session, SessionConfig


def init_session(session_config_path: Path, session_counter_path: Path) -> Session:
    session_config = ConfigStore(session_config_path, SessionConfig).value
    store = DailySessionIdStore(session_counter_path)

    animal_dict: dict[str, Animal] = {}
    for animal_config in session_config.animals:
        train_state = StageState(
            stage_name=animal_config.stage, level=animal_config.level
        )
        animal_state = Animal(
            rfid_id=animal_config.rfid_id,
            name=animal_config.name,
        )
        animal_state.set_current_stage(train_state)
        animal_dict[animal_config.name] = animal_state

    session = Session(
        session_id=store.session_id,
        experimenter=session_config.experimenter,
        reward_type=session_config.reward_type,
        send_email=False,
        sync_data=False,
        note=session_config.note,
        animals=animal_dict,
    )
    session.start()

    return session
