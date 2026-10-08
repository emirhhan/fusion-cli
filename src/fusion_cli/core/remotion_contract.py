"""Üretimden önce host tarafından kaydedilen açık kit sözleşmesi."""

from __future__ import annotations

from collections.abc import Callable
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


@dataclass(frozen=True, slots=True)
class KitContractSnapshot:
    registered: RegisteredKitContract | None
    revision: int


class KitContractState:
    """Doğrulayıcı kurulmasından sonra gelen araç kaydını oturum içinde korur."""

    def __init__(self) -> None:
        self._registered: RegisteredKitContract | None = None
        self._is_required = False
        self._history: list[RegisteredKitContract] = []
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

    def snapshot(self) -> KitContractSnapshot:
        """Aynı kayıt geri gelse bile ABA revizyonunu tek kilitte ayırt et."""
        with self._lock:
            return KitContractSnapshot(self._registered, len(self._history))

    @property
    def history(self) -> tuple[RegisteredKitContract, ...]:
        with self._lock:
            return tuple(self._history)

    def revise(
        self,
        expected: RegisteredKitContract,
        replacement: RegisteredKitContract,
        apply: Callable[[], None],
    ) -> None:
        """Host işlemi başarıyla bitmeden CAS kaydını ve geçmişi ilerletme."""
        with self._lock:
            if self._registered != expected:
                raise ValueError("Sahne revizyonunun host kaydı eskidi; yeniden planla.")
            if (
                replacement.project_dir != expected.project_dir
                or replacement.plan.entry != expected.plan.entry
                or replacement.plan.composition_id != expected.plan.composition_id
                or sum(scene.duration for scene in replacement.scenes)
                != sum(scene.duration for scene in expected.scenes)
            ):
                raise ValueError(
                    "Revizyon host kökünü, girişini, kimliğini ve toplam süreyi korumalı."
                )
            apply()
            if replacement == expected:
                return
            self._history.append(expected)
            self._registered = replacement

    @property
    def is_required(self) -> bool:
        with self._lock:
            return self._is_required

    def require(self) -> None:
        """Yalnız çağıranın açık kit planı kayıt yapılmadan başarıyı engeller."""
        with self._lock:
            self._is_required = True
