"""Model sağlık sondası önbelleği — diske yazılan, KISA ömürlü sonuç kaydı.

`fusion doctor --live` her modelin gerçekten yanıt verip vermediğini ölçer
(bkz. `providers/catalog.py::probe_nim_tools`, `cli/doctor.py::_live`). Bu ölçüm
model başına 60 saniyeye kadar sürebilir; model seçici HER açılışında bunu
yeniden yapamaz — kullanıcıyı dakikalarca bekletirdi.

Bu modül son sondaj sonucunu diske yazar ve seçici onu OKUR (ağa çıkmaz, tek bir
küçük JSON dosyasını açar). Sonuç `MODEL_HEALTH_CACHE_TTL_S` süresi boyunca
geçerli sayılır; süresi dolmuş ya da hiç sondanmamış model "bilinmiyor" kabul
edilir — sessizce "sağlıklı" ya da "sağlıksız" varsayılmaz.

Not: `core/health.py`'deki `ModelHealth` BAŞKA bir kavramdır — o, tur-içi circuit
breaker'ın oturuma bağlı, kalıcı OLMAYAN durumu. Bu modüldeki `ProbeResult` ise
`doctor --live`'ın DİSKE yazdığı, oturumlar arası kalıcı sondaj sonucudur.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.clock import SystemClock
from ..core.constants import MODEL_HEALTH_CACHE_TTL_S
from ..core.protocols import Clock

#: Önbellek dosyasının adı; `config.paths.user_data_dir()` altında durur.
HEALTH_CACHE_FILENAME = "model_health.json"


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """Bir modelin son sondaj sonucu."""

    model: str
    ok: bool
    #: Sondanın yapıldığı an (`Clock.now()`, epoch saniye).
    checked_at: float
    #: Kısa insan-okur açıklama (hata ya da "araç çağrısı doğru" gibi). Sır içermez.
    detail: str = ""


def _read_raw(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Dosya yok, bozuk ya da okunamıyor: boş önbellek sayılır. Sondaj
        # geçmişi bir iyileştirmedir, kaybı seçiciyi çökertmemeli.
        return {}
    return payload if isinstance(payload, dict) else {}


def load(path: Path) -> dict[str, ProbeResult]:
    """Önbelleği oku. Bozuk/eksik girdi sessizce atlanır."""
    raw = _read_raw(path)
    entries: dict[str, ProbeResult] = {}
    for model, value in raw.items():
        if not isinstance(value, dict):
            continue
        ok = value.get("ok")
        checked_at = value.get("checked_at")
        if not isinstance(ok, bool) or not isinstance(checked_at, (int, float)):
            continue
        detail = value.get("detail")
        entries[model] = ProbeResult(
            model=model,
            ok=ok,
            checked_at=float(checked_at),
            detail=detail if isinstance(detail, str) else "",
        )
    return entries


def save(path: Path, entries: dict[str, ProbeResult]) -> None:
    """Önbelleği diske yaz. Ebeveyn dizin yoksa oluşturulur."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        model: {"ok": result.ok, "checked_at": result.checked_at, "detail": result.detail}
        for model, result in entries.items()
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def record(
    path: Path,
    model: str,
    *,
    ok: bool,
    detail: str = "",
    clock: Clock | None = None,
) -> None:
    """Tek bir modelin sondaj sonucunu önbelleğe işle (var olanları korur)."""
    active_clock = clock or SystemClock()
    entries = load(path)
    entries[model] = ProbeResult(model=model, ok=ok, checked_at=active_clock.now(), detail=detail)
    save(path, entries)


def is_known_unhealthy(
    path: Path,
    model: str,
    *,
    ttl_s: float = MODEL_HEALTH_CACHE_TTL_S,
    clock: Clock | None = None,
) -> bool:
    """Model YAKIN ZAMANDA sondalanmış ve YANIT VERMEMİŞ mi?

    Süresi dolmuş ya da hiç kaydı olmayan model burada `False` döner —
    doğrulanmamış model "sağlıklı" sayılmaz ama "bilinen sağlıksız" da
    sayılmaz; bu ayrım `list_selectable_models`'ın modeli GİZLEMEK yerine
    yalnızca ETİKETLEMEK içindir.
    """
    active_clock = clock or SystemClock()
    result = load(path).get(model)
    if result is None or result.ok:
        return False
    return (active_clock.now() - result.checked_at) <= ttl_s
