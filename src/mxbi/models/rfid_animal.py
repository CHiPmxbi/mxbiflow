from pydantic import BaseModel, RootModel

from mxbi.config import Configure
from mxbi.path import ANIMAL_DB_PATH


class RFIDAnimal(BaseModel):
    name: str


class RFIDAnimals(RootModel):
    root: dict[str, RFIDAnimal]


animal_db = Configure(ANIMAL_DB_PATH, RFIDAnimals).value
