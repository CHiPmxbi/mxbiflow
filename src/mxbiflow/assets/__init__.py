from pathlib import Path

from .background import create_background as create_background
from .corner_button import Corner as Corner
from .corner_button import CornerButton as CornerButton
from .image_sprite import ImageSprite as ImageSprite
from .result_widget import ResultWidget as ResultWidget

ROOT = Path(__file__).parent

_AUDIO_DIR = ROOT / "audio"
_IMAGE_DIR = ROOT / "images"

CLICKER_PATH = _AUDIO_DIR / "clicker.wav"
APPLE_IMAGES = sorted(_IMAGE_DIR.glob("*.png"))

__all__ = [
    "APPLE_IMAGES",
    "CLICKER_PATH",
    "ROOT",
    "Corner",
    "CornerButton",
    "ImageSprite",
    "ResultWidget",
    "create_background",
]
