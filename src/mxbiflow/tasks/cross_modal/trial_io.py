from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_TRIAL_INDEX_CACHE: dict[tuple[Path, str], int] = {}


@dataclass(frozen=True)
class TrialCursor:
    bundle_root: Path
    subject_id: str

    def next_index(self, trial_count: int) -> int:
        if trial_count <= 0:
            raise ValueError("trial_count must be > 0")
        key = (self.bundle_root.resolve(), self.subject_id)
        idx = _TRIAL_INDEX_CACHE.get(key, 0)
        return idx % trial_count

    def advance(self, last_index: int) -> None:
        key = (self.bundle_root.resolve(), self.subject_id)
        _TRIAL_INDEX_CACHE[key] = last_index + 1
