"""Hakem çıktısının ayrıştırılması.

Ayrıştırma saf bir fonksiyondur: ağ yok, yan etki yok, doğrudan test edilir.

Model çıktısı üç şekilde kirlenebilir ve üçü de burada temizlenir:
1. Reasoning modelleri cevabı `<think>…</think>` bloklarıyla sarar.
2. Bazı modeller JSON'u ```json çitleri içine alır.
3. Model JSON'dan önce ya da sonra açıklama yazar.

Bu yüzden metindeki DENGELİ süslü parantez blokları taranır ve SONDAN başlayarak
ilk geçerli olan kabul edilir (düşünme bölümünden sonra gelen gerçek cevap odur).
Hiçbiri ayrıştırılamazsa hata fırlatılmaz: sezgisel kazanan (ilk geçerli aday)
seçilir ve `parsed=False` ile işaretlenir — tur asla durmaz.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Sequence

from ...core.types import Verdict

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)
_CODE_FENCE = re.compile(r"```(?:json)?\s*|\s*```")

FALLBACK_REASON = "Hakem çıktısı ayrıştırılamadı; ilk geçerli aday seçildi."


def parse_verdict(text: str, valid_names: Sequence[str]) -> Verdict:
    """Hakem metnini karara çevir. Ayrıştırılamazsa ilk geçerli adaya düşer."""
    if not valid_names:
        raise ValueError("parse_verdict için en az bir geçerli aday adı gerekir.")

    cleaned = _CODE_FENCE.sub("", _THINK_BLOCK.sub("", text or ""))
    allowed = set(valid_names)

    for blob in reversed(list(iter_json_objects(cleaned))):
        try:
            data = json.loads(blob)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        winner = data.get("winner")
        if not isinstance(winner, str) or winner not in allowed:
            continue
        return Verdict(
            winner=winner,
            scores=_clean_scores(data.get("scores"), allowed),
            reason=str(data.get("reason", "")).strip(),
            parsed=True,
        )

    return Verdict(winner=valid_names[0], scores={}, reason=FALLBACK_REASON, parsed=False)


def iter_json_objects(text: str) -> Iterator[str]:
    """Metindeki dengeli `{...}` bloklarını baştan sona üret.

    Basit bir tarayıcıdır ama dize içindeki süslü parantezleri ve kaçış karakterlerini
    doğru atlar; bu yüzden JSON'un içinde `{` geçen bir metin varsa yanılmaz.
    """
    depth = 0
    start = -1
    in_string = False
    escaped = False

    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start >= 0:
                yield text[start : index + 1]


def _clean_scores(raw: object, allowed: set[str]) -> dict[str, float]:
    """Yalnızca geçerli aday adlarına ait, sayıya çevrilebilen puanları al."""
    if not isinstance(raw, dict):
        return {}
    scores: dict[str, float] = {}
    for name, value in raw.items():
        if name not in allowed or isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            scores[str(name)] = max(0.0, min(1.0, float(value)))
    return scores
