"""`/code-review` bulgu listesi (#214, Claude Code ReportFindings).

Claude Code: bulgu listesi isteyen bir ana uygulamada (masaüstü uygulaması gibi) inceleme
sonuçları metin yerine ReportFindings aracıyla tipli liste olarak bildirilir; uygulama onları
kart olarak çizer. İstek her seviyede geçerlidir.

Fusion: masaüstü oturumu `ReplState.findings_host`'u açar; `/code-review` görevi o zaman
modelden bulguları cevabın sonunda tek bir ```findings bloğunda JSON dizisi olarak ister
(araç şeması eklenmez: araç istemi bütçesi korunur). Masaüstü tur sonunda bloğu ayıklar,
doğrular, metinden çıkarır ve `bulgular` alanıyla arayüze verir; arayüz kartları çizer.
Terminal yüzeyleri metin raporunu aynen gösterir. Blok okunamazsa metin olduğu gibi kalır.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

#: Görev metnindeki işaret: masaüstü bu turun bulgu listesi beklediğini buradan anlar.
HOST_MARKER = "[bulgu-listesi]"
HOST_REQUEST = (
    f"{HOST_MARKER} Bu oturum bulgu listesi isteyen bir uygulamadır (Claude Code ReportFindings). "
    "Bulguları düzyazı liste yerine cevabının SONUNDA tek bir ```findings kod bloğunda JSON "
    'dizisi olarak ver; her öğe: {"file": göreli yol, "line": satır (1 tabanlı), "summary": '
    'tek cümle kusur, "failure_scenario": somut girdi/durum → yanlış çıktı/çökme, '
    '"short_summary": en çok 60 karakter, "category": kısa kebab-case tür, '
    '"verdict": "CONFIRMED" ya da "PLAUSIBLE"}. En ciddiden başla; bulgu yoksa boş dizi `[]`. '
    "Bloktan önce en çok iki cümlelik özet yaz."
)
#: Claude Code ReportFindings tavanı.
MAX_FINDINGS = 32
VERDICTS = frozenset({"CONFIRMED", "PLAUSIBLE"})
_BLOCK = re.compile(r"```findings[ \t]*\n(.*?)```", re.DOTALL)
NO_FINDINGS = "İnceleme bitti: doğrulanan bulgu yok."


@dataclass(frozen=True, slots=True)
class Extracted:
    text: str
    findings: tuple[dict[str, object], ...]


def _text(item: dict[str, object], key: str, limit: int) -> str:
    value = item.get(key)
    return value.strip()[:limit] if isinstance(value, str) else ""


def _finding(item: object) -> dict[str, object] | None:
    """Tek bulguyu ReportFindings şemasına göre doğrula; zorunlu alan eksikse None."""
    if not isinstance(item, dict):
        return None
    file, summary = _text(item, "file", 400), _text(item, "summary", 600)
    scenario = _text(item, "failure_scenario", 1200)
    line = item.get("line")
    if isinstance(line, str) and line.strip().isdigit():
        line = int(line)
    if not (file and summary and scenario) or not isinstance(line, int) or isinstance(line, bool):
        return None
    finding: dict[str, object] = {
        "file": file,
        "line": max(1, line),
        "summary": summary,
        "failure_scenario": scenario,
    }
    for key, limit in (("short_summary", 60), ("category", 40)):
        if value := _text(item, key, limit):
            finding[key] = value
    verdict = _text(item, "verdict", 20).upper()
    if verdict in VERDICTS:
        finding["verdict"] = verdict
    return finding


def extract(text: str) -> Extracted | None:
    """Son ```findings bloğunu ayıkla; blok yoksa ya da JSON dizisi değilse None."""
    matches = list(_BLOCK.finditer(text))
    if not matches:
        return None
    block = matches[-1]
    try:
        raw = json.loads(block.group(1))
    except ValueError:
        return None
    if not isinstance(raw, list):
        return None
    findings = tuple(f for f in (_finding(item) for item in raw) if f is not None)
    cleaned = (text[: block.start()] + text[block.end() :]).strip()
    if not cleaned and not findings:
        cleaned = NO_FINDINGS
    return Extracted(cleaned, findings[:MAX_FINDINGS])


def is_findings_turn(task: str) -> bool:
    return HOST_MARKER in task
