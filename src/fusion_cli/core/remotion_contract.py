"""Üretimden önce host tarafından kaydedilen açık kit sözleşmesi."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from .repair_ledger import SourceFingerprint


@dataclass(frozen=True, slots=True)
class KitFramePlan:
    frame: int
    scene_id: str
    artifact: str
    requires_feature: bool = True


@dataclass(frozen=True, slots=True)
class KitVerificationPlan:
    entry: str
    composition_id: str
    sources: tuple[str, ...]
    timeout_s: float
    samples: tuple[KitFramePlan, ...]


@dataclass(frozen=True, slots=True)
class KitScenePlan:
    scene_id: str
    kind: str
    duration: int


@dataclass(frozen=True, slots=True)
class RegisteredKitContract:
    plan: KitVerificationPlan
    scenes: tuple[KitScenePlan, ...]
    packaged_sources: tuple[SourceFingerprint, ...]
    project_dir: str = "."


class KitContractState:
    """Doğrulayıcı kurulmasından sonra gelen araç kaydını oturum içinde korur."""

    def __init__(self) -> None:
        self._registered: RegisteredKitContract | None = None
        self._lock = Lock()

    @property
    def registered(self) -> RegisteredKitContract | None:
        with self._lock:
            return self._registered

    def register(self, contract: RegisteredKitContract) -> None:
        """Modelin sonraki dosya/JSON değişimi ilk host beklentisini değiştiremez."""
        with self._lock:
            if self._registered is not None and self._registered != contract:
                raise ValueError("Bu oturumda farklı kit sözleşmesi zaten kayıtlı.")
            self._registered = contract
