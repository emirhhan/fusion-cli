"""Platform observer'ını kabul Inspection'a bağla; eksik route başarı değildir.

Bu modül kayıt defteri/runner/brief değiştirmez. DOM sözleşmesi olmayan canvas
oyunları, erişilemeyen route ve tuşsuz kontrol yetersizliği açık ölçüm eksiğidir.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from evals.kabul.areas._browser import BrowserUnavailableError, navigate, open_page
from evals.kabul.areas.platform_observer import (
    ObservedRoute,
    PlatformPage,
    RouteStep,
    collect_trace,
)
from evals.kabul.areas.platform_trace import (
    PlatformTraceReport,
    TraceCriterion,
    TraceStatus,
    verify_trace,
)
from evals.kabul.model import Check, Inspection


@dataclass(frozen=True, slots=True)
class PlatformInspection:
    inspection: Inspection
    trace: PlatformTraceReport
    capture: ObservedRoute


def _json_value(value: object) -> list[str]:
    if isinstance(value, frozenset) and all(isinstance(item, str) for item in value):
        return sorted(value)
    raise TypeError("Observer JSON değeri desteklenmiyor.")


def inspect_pages(
    play: PlatformPage,
    idle: PlatformPage | None,
    route: tuple[RouteStep, ...],
    output: Path,
    *,
    source_digest: str,
) -> PlatformInspection:
    """Gerçek Page gözlemleri ve kareler; saf iz sonucu ürün kalitesi yerine konmaz."""
    capture = collect_trace(play, idle, route, output, source_digest=source_digest)
    measured = verify_trace(capture.events)
    integrity = TraceStatus.UNVERIFIED if capture.unverified_steps else TraceStatus.PASSED
    trace = PlatformTraceReport(
        (*measured.criteria, TraceCriterion("observer_integrity", integrity))
    )
    checks = tuple(
        Check(
            item.name,
            item.status is TraceStatus.PASSED,
            f"platform gözlem durumu: {item.status.value}",
        )
        for item in trace.criteria
        if item.status is not TraceStatus.UNVERIFIED
    )
    incomplete = capture.unverified_steps or any(
        item.status is TraceStatus.UNVERIFIED for item in trace.criteria
    )
    reason = ""
    if incomplete and trace.status is not TraceStatus.FAILED:
        reason = (
            "Platform ölçümü eksik: gerçek route/DOM/kontrol gözlemi doğrulanmadı; "
            "canvas veya state kancası tek başına semantik PASS vermez."
        )
    inspection = Inspection(checks, invalid_reason=reason)
    payload = {
        "schema": "fusion-platform-observation-v1",
        "source_digest": source_digest,
        "capture": asdict(capture),
        "trace": asdict(trace),
        "inspection": asdict(inspection),
        "quality_verified": False,
        "limitations": [
            "DOM marker sözleşmesi gerekir; canvas/OCR desteklenmez.",
            "Source digest yalnız index.html'dir, tüm kaynaklar değildir.",
            "Tam route veya eşleşen idle olmadan başarı verilmez.",
        ],
    }
    (output / "platform-observation.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_value), encoding="utf-8"
    )
    return PlatformInspection(inspection, trace, capture)


def inspect_platform(root: Path, route: tuple[RouteStep, ...]) -> Inspection:
    """Yerel HTTP gerçek sayfası; browser/konsol ile ürün kusuru ayrı kalır.

    File protokolü ve bağımsız kontrollü idle-prefix yürütmesi henüz burada yok;
    bu adapter tüm platform/brief kabulünü tamamladığını iddia etmez.
    """
    if not route:
        return Inspection(invalid_reason="Platform route hazır değil; oynama ölçülmedi.")
    index = root / "index.html"
    if index.is_symlink() or not index.is_file():
        return Inspection(checks=(Check("index.html", False, "Normal public giriş dosyası yok."),))
    digest = hashlib.sha256(index.read_bytes()).hexdigest()
    try:
        with open_page(root) as opened:
            navigate(opened)
            result = inspect_pages(
                opened.page, None, route, root / "platform-observation", source_digest=digest
            )
            errors = opened.console.errors
    except BrowserUnavailableError as error:
        return Inspection(invalid_reason=str(error))
    if errors:
        return Inspection(
            (
                *result.inspection.checks,
                Check("console_errors", False, "Konsol/pageerror gözlendi."),
            )
        )
    return result.inspection
