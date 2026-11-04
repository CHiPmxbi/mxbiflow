from pydantic import BaseModel, Field


class MXBIDatabase(BaseModel):
    experimenter: list[str] = Field(default_factory=list, frozen=True)
    # RFID tag to animal name, the animals of offline mode.
    animals: dict[str, str] = Field(default_factory=dict, frozen=True)
