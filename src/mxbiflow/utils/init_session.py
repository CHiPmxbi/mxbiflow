from ..config_store import ConfigStore
from ..models.animal import Animal, StageState
from ..models.session import DailySessionIdStore, Session, SessionConfig
from ..path import get_config_session_path, get_session_counter_path


def init_session() -> Session:
    session_config = ConfigStore(get_config_session_path(), SessionConfig).value
    store = DailySessionIdStore(get_session_counter_path())

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
        default_scene=session_config.default_scene,
        unknown_animal_fallback=session_config.unknown_animal_fallback,
        fault_fallback=session_config.fault_fallback,
        animals=animal_dict,
    )
    session.start()

    return session
