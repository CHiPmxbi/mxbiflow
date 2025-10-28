from configure import Configure
from pydantic import BaseModel

from tools.sync_data.constant import CONFIG_DIR_PATH, SAMBA_CONFIG


class SambaConfig(BaseModel):
    username: str | None = None
    server: str | None = None
    share_path: str | None = None


samba_config = Configure(CONFIG_DIR_PATH / SAMBA_CONFIG, SambaConfig)
