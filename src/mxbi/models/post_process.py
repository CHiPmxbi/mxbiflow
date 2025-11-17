from pathlib import Path

from pydantic import BaseModel


class PostProcessConfig(BaseModel):
    data_path: Path
