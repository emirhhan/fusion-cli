"""Öğretmen öncesi görev kararı ve yapılandırılmış plan sözleşmesi."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from ..effects.detect import required_effect_for
from ..effects.model import EffectKind


@dataclass(frozen=True, slots=True)
class TeacherTaskDecision:
    """Öğretmene önceden danışmanın gerekli olup olmadığı."""

    size: str
    reasons: tuple[str, ...]


def classify_teacher_task(task: str) -> TeacherTaskDecision:
    """Mevcut etki kararı ile görevin yapısal kapsamını birlikte kullan."""
    effect = required_effect_for(task)
    reasons: list[str] = []
    if effect == EffectKind.WORKSPACE_MUTATION.value:
        reasons.append(f"istenen etki: {effect}")
    # Dış API bağımlılığı ad listesinden tahmin edilmez: istek açıkça API
    # entegrasyonu söylüyorsa öğretmenin yapılabilirlik planı gereklidir.
    if re.search(r"\bAPI\b", task, re.IGNORECASE) and not task.strip().endswith("?"):
        reasons.append("dış API bağımlılığı")
    # Birden fazla numaralı madde, sözcük tahmini olmadan açık bir iş dizisidir.
    if len(re.findall(r"(?m)^\s*\d+[.)]\s+", task)) > 1:
        reasons.append("birden fazla açık adım")
    return TeacherTaskDecision(
        size="orta-buyuk" if reasons else "basit",
        reasons=tuple(reasons),
    )


@dataclass(frozen=True, slots=True)
class UnworkablePart:
    """Dış kısıt yüzünden yapılamayan iş ve uygulanabilir yol."""

    topic: str
    reason: str
    alternative: str


@dataclass(frozen=True, slots=True)
class TeacherPlan:
    """Öğretmenin uygulanabilir ve doğrulanabilir görev planı."""

    steps: tuple[str, ...]
    files: tuple[str, ...]
    risks: tuple[str, ...]
    unworkables: tuple[UnworkablePart, ...]
    verification: tuple[str, ...]
    raw: str


class TeacherPlanError(ValueError):
    """Öğretmen yanıtı plan sözleşmesine uymuyor."""


def _string_items(value: object, field: str, *, required: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise TeacherPlanError(f"'{field}' metin dizisi olmalı.")
    items = tuple(item.strip() for item in value if item.strip())
    if required and not items:
        raise TeacherPlanError(f"'{field}' en az bir madde içermeli.")
    return items


def parse_teacher_plan(answer: str) -> TeacherPlan:
    """Önek ve kod çiti içinden ilk geçerli JSON planını ayıkla."""
    document = _json_document(answer, "adimlar")
    steps = _string_items(document.get("adimlar"), "adimlar", required=True)
    files = _string_items(document.get("dosyalar"), "dosyalar")
    risks = _string_items(document.get("riskler"), "riskler")
    verification = _string_items(document.get("dogrulama"), "dogrulama")
    raw_unworkables = document.get("yapilamayanlar")
    if not isinstance(raw_unworkables, list):
        raise TeacherPlanError("'yapilamayanlar' dizi olmalı.")
    unworkables: list[UnworkablePart] = []
    for item in raw_unworkables:
        if not isinstance(item, dict) or any(
            not isinstance(item.get(key), str) or not item[key].strip()
            for key in ("konu", "gerekce", "alternatif")
        ):
            raise TeacherPlanError("Yapılamayan iş için konu, gerekçe ve alternatif gerekli.")
        unworkables.append(
            UnworkablePart(
                topic=item["konu"].strip(),
                reason=item["gerekce"].strip(),
                alternative=item["alternatif"].strip(),
            )
        )
    return TeacherPlan(steps, files, risks, tuple(unworkables), verification, answer)


def _json_document(answer: str, marker: str) -> dict[str, object]:
    """Açıklama ve kod çitleri arasındaki ilk uygun JSON nesnesini bul."""
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", answer):
        try:
            candidate, _end = decoder.raw_decode(answer[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and marker in candidate:
            return candidate
    raise TeacherPlanError(f"Öğretmen yanıtında '{marker}' alanlı JSON bulunamadı.")


def parse_teacher_review(answer: str) -> tuple[str, ...]:
    """Yalnız açık JSON bulgularını denetim sonucu kabul et."""
    document = _json_document(answer, "bulgular")
    return _string_items(document.get("bulgular"), "bulgular")
