"""Adım doğrulama kapısı önbelleği (A4-16).

Her plan adımında TAM proje kapısı (`deps.verifier.verify()`: build komutu, tarayıcı,
site probu) koşuyordu; N adımlı planda N+1 tam build. Ölçüldü (30 Ekim): salt okuma
adımı (`step_mutates` yok, hiçbir yazma aracı çağrılmadı) çalışma alanını DEĞİŞTİRMEZ,
dolayısıyla bir önceki geçen kapının sonucu aynen geçerlidir.

Güvenlik kuralları:

- Yalnız GEÇEN (`ok=True`) sonuç önbelleğe alınır; düşen kapı her seferinde yeniden ölçülür.
- Yalnız mutasyonsuz adımda kullanılır: planda `workspace_mutation`/`file:`/`shell_action`/
  git etkisi varsa ya da adım bir yazma aracı çağırdıysa kapı HER ZAMAN tam koşar.
- Anahtar, dokunulan dosyaların (yol, mtime_ns, boyut) parmak izidir; biri değişirse
  isabet olmaz.
- Kayıt kısa ömürlüdür (`ttl_s`): dış durum (site, tarayıcı) uzun süre geçtiyse yeniden ölçülür.
- FİNAL kabul kapısı bu önbelleği ASLA kullanmaz; `verify_step` dışında çağrılır ve her
  zaman tam koşar.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from ...core.execution_plan import PlanStep
from ...core.verification import VerificationResult

#: Önbellek kaydının en uzun ömrü (sn).
DEFAULT_TTL_S = 300.0

#: Çalışma alanını değiştirebilecek beklenen etkiler.
_MUTATING_EFFECTS = frozenset({"workspace_mutation", "shell_action", "git_commit", "git_push"})


def step_mutates(step: PlanStep) -> bool:
    """Adımın planı çalışma alanını değiştirmeyi vaat ediyor mu?"""
    return any(
        effect in _MUTATING_EFFECTS or effect.startswith("file:")
        for effect in step.expected_effects
    )


def workspace_key(paths: Iterable[Path]) -> str:
    """Dokunulan dosyaların durumundan kısa bir parmak izi üret."""
    digest = hashlib.sha256()
    for path in sorted(set(paths)):
        try:
            stat = path.stat()
            state = f"{stat.st_mtime_ns}:{stat.st_size}"
        except OSError:
            state = "yok"
        digest.update(f"{path}\0{state}\0".encode())
    return digest.hexdigest()


@dataclass
class GateCache:
    """Son GEÇEN kapı sonucunu çalışma alanı parmak iziyle sakla."""

    ttl_s: float = DEFAULT_TTL_S
    clock: Callable[[], float] = time.monotonic
    hits: int = 0
    _entry: tuple[str, float, VerificationResult] | None = field(default=None, repr=False)

    def lookup(self, key: str) -> VerificationResult | None:
        if self._entry is None:
            return None
        stored_key, stored_at, result = self._entry
        if stored_key != key or self.clock() - stored_at > self.ttl_s:
            return None
        self.hits += 1
        return result

    def store(self, key: str, result: VerificationResult) -> None:
        if result.ok:
            self._entry = (key, self.clock(), result)
        else:
            self._entry = None


@dataclass(frozen=True, slots=True)
class GateScope:
    """`verify_step`e verilen önbellek bağlamı.

    `outer_touched`, plana şimdiye dek ONAYLANMIŞ adımların dokunduğu dosyalardır; adımın
    kendi `touched` kümesi ayrı bir bağlamdadır ve doğrulamadan sonra buraya eklenir.
    """

    cache: GateCache
    outer_touched: frozenset[Path] = frozenset()
