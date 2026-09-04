"""Agent görevlerinin profesyonel yürütme modları."""

from __future__ import annotations

from enum import Enum


class ExecutionMode(Enum):
    """Kök görevin hızlı ve planlı yollar arasında nasıl seçileceği."""

    AUTO = "auto"
    ALWAYS = "always"
    OFF = "off"

    @classmethod
    def _missing_(cls, value: object) -> ExecutionMode | None:
        """Eski boolean ayarları güvenli yeni davranışa taşı."""
        if value is False:
            return cls.AUTO
        if value is True:
            return cls.ALWAYS
        return None
