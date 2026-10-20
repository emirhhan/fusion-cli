"""Auto profil — istek metninden uygun execution profilini seçer.

`/mode auto` açıkken her tur bu modül çalışır: görevi sınıflandırır, karmaşıklık
işaretlerini tartar ve `low`/`medium`/`high`/`max` profillerinden birini GEREKÇESİYLE
döndürür. Karar açıklanabilir olmalıdır (master prompt §7.2): kullanıcı neden o
profilin seçildiğini görebilmeli ve isterse elle geçersiz kılabilmelidir.

Saftır ve deterministiktir: model çağrısı YOK, yalnızca sınıflandırma + anahtar
kelime kuralları. İkinci bir sınıflandırıcı yazılmaz; mevcut `classify_task`
yeniden kullanılır (RULES.md "aynı işi yapan ikinci yol açılmaz").
"""

from __future__ import annotations

from dataclasses import dataclass

from .classify import TaskKind, classify_task

#: Profil merdiveni, en düşükten en yükseğe. İndeks karmaşıklık skorudur.
#: `ultra` bilinçli olarak DIŞARIDADIR: auto dört basamaklı sade bir model sunar
#: (master prompt low/medium/high/max); `ultra` elle seçilebilen bir ara basamaktır.
_LADDER: tuple[str, ...] = ("low", "medium", "high", "max")

#: Temel profili `low` olan görev türleri: okuma/açıklama/belge ağırlıklı, düşük risk.
_BASE_LOW: frozenset[TaskKind] = frozenset({TaskKind.EXPLORE, TaskKind.DOCS})

#: Karmaşıklık/yük yükselten işaretler. Her biri skoru bir basamak artırır; toplam
#: katkı iki basamakla sınırlıdır (tek bir "mimari" görevi doğrudan max'e fırlamasın).
_ESCALATION_SIGNALS: tuple[str, ...] = (
    "mimari",
    "architecture",
    "yeniden tasarla",
    "redesign",
    "tüm proje",
    "tum proje",
    "tüm mimari",
    "tum mimari",
    "tüm sistem",
    "tum sistem",
    "dağıtık",
    "dagitik",
    "distributed",
    "ölçeklen",
    "olceklen",
    "scalab",
    "eşzamanlı",
    "eszamanli",
    "concurren",
    "race condition",
    "güvenlik açığı",
    "guvenlik acigi",
    "kritik",
)

#: Görevi önemsizleştiren işaretler: tek başına profili bir basamak DÜŞÜRÜR.
_TRIVIAL_SIGNALS: tuple[str, ...] = (
    "adını değiştir",
    "adini degistir",
    "rename",
    "yeniden adlandır",
    "yeniden adlandir",
    "typo",
    "yazım hatası",
    "yazim hatasi",
    "tek satır",
    "tek satir",
    "küçük düzeltme",
    "kucuk duzeltme",
)

#: Karmaşıklık katkısının üst sınırı (basamak).
_MAX_ESCALATION = 2


@dataclass(frozen=True, slots=True)
class AutoChoice:
    """Auto seçimin sonucu: profil adı ve Türkçe gerekçe."""

    profile: str
    reason: str


def auto_profile(task_text: str) -> AutoChoice:
    """İstek metnine göre bir execution profili seç ve gerekçesini üret."""
    kind = classify_task(task_text)
    text = task_text.casefold()

    base = 0 if kind in _BASE_LOW else 1
    matched_escalation = tuple(signal for signal in _ESCALATION_SIGNALS if signal in text)
    matched_trivial = tuple(signal for signal in _TRIVIAL_SIGNALS if signal in text)
    escalation = min(_MAX_ESCALATION, len(matched_escalation))
    trivial = 1 if matched_trivial else 0

    score = max(0, min(len(_LADDER) - 1, base + escalation - trivial))
    return AutoChoice(_LADDER[score], _build_reason(kind, matched_escalation, matched_trivial))


def _build_reason(
    kind: TaskKind,
    escalation: tuple[str, ...],
    trivial: tuple[str, ...],
) -> str:
    """Seçim gerekçesini insanın okuyabileceği Türkçe bir cümleye çevir."""
    parts = [f"görev türü: {kind.value}"]
    if escalation:
        parts.append(f"karmaşıklık işaretleri: {', '.join(escalation)}")
    if trivial:
        parts.append(f"basit iş işaretleri: {', '.join(trivial)}")
    return "; ".join(parts)
