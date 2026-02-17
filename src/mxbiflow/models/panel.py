from pydantic import BaseModel, Field


class MXBIPanelConfig(BaseModel):
    auto_accept_timeout_seconds: int = Field(default=60, ge=0)
