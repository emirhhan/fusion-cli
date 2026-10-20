"""Host tarafından seçilmiş tarayıcı; araç veya model bağımlılığı içermez."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True, slots=True)
class RemotionBrowser:
    """Yalnız host taşır; executable varlığı taşıma sınırında doğrulanır."""

    executable: Path
    mode: Literal["headless-shell", "chrome-for-testing"]
