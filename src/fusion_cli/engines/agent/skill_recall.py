"""Görev tipine göre deterministik skill hatırlama.

Modelin `find_skill` çağırmasını UMUT ETMEK zayıf bir kaldıraçtır: sistem promptuna
kütüphane duyurusu eklendikten sonra bile 3 koşunun yalnızca 1'inde çağrıldı. Buna
karşılık DERSLER tur öncesi otomatik hatırlanıyor ve prompta enjekte ediliyor —
modelin tercihine bırakılmıyor. Skill'ler için aynı simetri kurulur.

Sorgu neden görev metninden değil görev TÜRÜNDEN üretilir: kullanıcı Türkçe yazıyor,
skill açıklamaları İngilizce. Anahtar kelime araması bu ikisini eşleştiremez —
ölçüldü, Türkçe görev `laravel-plugin-discovery` ve `quarkus-patterns` getiriyordu.
Sınıflandırıcının ürettiği tür bu köprüyü dil bağımsız kurar.

Tür belirsizse (GENERAL, EXPLORE) hiçbir şey enjekte edilmez: yanlış uzmanlığı prompta
koymak, hiç koymamaktan kötüdür.
"""

from __future__ import annotations

import re
from pathlib import Path

from ...tools.capabilities import Capability, load_skill_text, search
from .classify import TaskClassification, TaskKind

#: Fusion'a ait, göreve göre eklenen referans metinleri.
#:
#: Kullanıcının kütüphanesindeki tasarım skill'leri soyut öğüt verir ("choose a
#: direction", "prefer contextual typography"); model bunları yükleyip yine jenerik
#: çıktı üretiyor, çünkü sıfat kopyalanamaz. Buradaki referans SOMUT ölçek taşır
#: (boşluk, tipografi, yarıçap, gölge, bileşen ölçüleri) ve fusion'a aittir —
#: kullanıcının kurulumuna bağlı değildir.
_REFERENCES: dict[TaskKind, str] = {TaskKind.WEBSITE: "web_reference.md"}
_PROMPTS = Path(__file__).parent / "prompts"

#: Görev türü → skill kütüphanesinde aranacak İngilizce terimler.
#:
#: Yalnızca uzmanlığın ne olduğunun BELLİ olduğu türler eşlenir. Belirsiz türlerde
#: tahmin yürütmek yerine hiç enjekte edilmez.
SKILL_QUERIES: dict[TaskKind, str] = {
    TaskKind.WEBSITE: "frontend design css responsive ui web page",
    TaskKind.TEST: "testing test patterns coverage",
    TaskKind.BUGFIX: "debugging error handling",
    TaskKind.REFACTOR: "refactoring code quality patterns",
    TaskKind.DOCS: "documentation writing prose",
}

#: Enjekte edilen skill metnine tanınan bütçe. Tam bir SKILL.md 6.000 karaktere kadar
#: çıkabiliyor; sistem promptunu bir uzmanlık metniyle doldurmak diğer talimatları
#: gölgeler. Yönü verecek kadarı yeter, tamamı değil.
INJECT_BUDGET = 2_500

#: Fusion'ın kendi referans metnine tanınan bütçe.
#:
#: Ölçüldü: `web_reference.md` 20.877 karakter ve kırpılmadan enjekte ediliyordu,
#: oysa kullanıcının skill'i 2.500 ile sınırlıydı — 8,3 kat asimetri. Tarayıcı
#: mesaj kutusunun tavanı 32.316 karakter (deneyle ölçüldü), promptun geri kalanı
#: toplam prompt bağlamını da büyütür; bu yüzden otomatik yol daha dar bütçe kullanır.
#: Geriye kalan pay budur; tavana dayanmamak için üstü değil altı seçilir.
REFERENCE_BUDGET = 6_000

#: OTOMATİK enjeksiyon direct API'den daha dar bütçe kullanır.
#:
#: `reference_block()` ve `as_prompt_block()` doğrudan çağrıldığında geriye uyumlu
#: büyük bütçeler korunur. Agent loop ise ham modelin dikkat bütçesini korumak için
#: aşağıdaki daha küçük sınırları kullanır.
AUTO_SKILL_BUDGET = 1_600
AUTO_REFERENCE_BUDGET = 3_200

#: Primary ile ikinci niyet birbirine çok yakınsa classifier `confidence` düşük olur.
#: Böyle bir durumda yanlış uzmanlığı sisteme basmak, hiç basmamaktan daha zararlıdır.
AUTO_MIN_CONFIDENCE = 0.20

#: Bazı doğal görevlerde primary ve FEATURE birlikte güçlüdür:
#: "landing page oluştur" gibi. Confidence marjı küçük olsa bile primary'nin mutlak
#: skoru çok kuvvetliyse otomatik context'e izin verilir.
AUTO_STRONG_PRIMARY_SCORE = 6


def should_auto_context(classification: TaskClassification) -> bool:
    """Otomatik lesson/skill/reference enjeksiyonu güvenli mi?

    GENERAL/EXPLORE doğası gereği belirsizdir. Diğer türlerde classifier ya yeterli
    marja sahip olmalı ya da primary için çok güçlü deterministik kanıt görmelidir.
    """

    if classification.primary in {TaskKind.GENERAL, TaskKind.EXPLORE}:
        return False

    return (
        classification.confidence >= AUTO_MIN_CONFIDENCE
        or classification.score_for(classification.primary) >= AUTO_STRONG_PRIMARY_SCORE
    )


def should_auto_skill(classification: TaskClassification) -> bool:
    """Primary tür için otomatik kullanıcı skill'i enjekte edilmeli mi?"""

    return should_auto_context(classification) and classification.primary in SKILL_QUERIES


def should_auto_reference(classification: TaskClassification) -> bool:
    """Fusion'ın kendi görev referansı otomatik enjekte edilmeli mi?"""

    return should_auto_context(classification) and classification.primary in _REFERENCES


def skill_query(kind: TaskKind) -> str:
    """Görev türüne karşılık gelen arama terimleri; belirsiz türde boş."""
    return SKILL_QUERIES.get(kind, "")


def select_skill(skills: tuple[Capability, ...], kind: TaskKind) -> Capability | None:
    """Türe en uygun TEK skill'i seç; eşleşme yoksa None.

    Tek seçilir: birden çok uzmanlık metnini üst üste koymak bağlamı şişirir ve
    hangisine uyulacağı belirsizleşir.
    """
    query = skill_query(kind)
    if not query or not skills:
        return None
    matches = search(skills, query, limit=1)
    return matches[0] if matches else None


def as_prompt_block(
    skill: Capability | None,
    *,
    budget: int = INJECT_BUDGET,
) -> str:
    """Seçilen skill'i sistem promptuna eklenecek bloğa çevir; yoksa boş metin."""
    if skill is None:
        return ""
    text = load_skill_text(skill.path, budget=budget).strip()
    if not text:
        return ""
    return f"# Uzmanlık talimatı: {skill.name}\n{text}"


def reference_block(kind: TaskKind, budget: int = REFERENCE_BUDGET) -> str:
    """Görev türüne ait fusion referansı, bütçeye indirilmiş hâlde; yoksa boş metin.

    Bütçe düz karakter kesmesiyle uygulanamaz: dosya ölçek tabloları ve kod
    örnekleri taşır, tablonun ortasından kesmek modele yarım satır bırakır ve
    "bu sayıyı kullan" diyen bir referansta bu, uydurmaya davettir. Bu yüzden
    BÜTÜN bölümler alınır; sığmayan bölüm hiç girmez.

    Bölümler dosya sırasıyla alınır çünkü dosya temelden ayrıntıya yazılmıştır:
    ölçekler ve renk disiplini başta, uzun örnek galerileri sonda.
    """
    dosya = _REFERENCES.get(kind)
    if dosya is None:
        return ""
    try:
        metin = (_PROMPTS / dosya).read_text(encoding="utf-8").strip()
    except OSError:
        # Referans okunamıyorsa tur devam eder; bu bir iyileştirmedir.
        return ""
    if len(metin) <= budget:
        return metin
    secilen: list[str] = []
    uzunluk = 0
    for bolum in re.split(r"(?m)^(?=## )", metin):
        if not bolum.strip():
            continue
        if uzunluk + len(bolum) > budget:
            break
        secilen.append(bolum)
        uzunluk += len(bolum)
    return "".join(secilen).strip()


def auto_expertise_block(
    classification: TaskClassification,
    skills: tuple[Capability, ...] = (),
) -> str:
    """Agent loop için confidence-gated, bütçeli expertise bloğu.

    Reference ve kullanıcı skill'i yalnız primary uzmanlığı yeterince güvenliyse
    eklenir. İkisi de direct API'deki maksimum bütçeden daha küçük otomatik bütçe
    kullanır.
    """

    parts: list[str] = []

    if should_auto_reference(classification):
        reference = reference_block(
            classification.primary,
            budget=AUTO_REFERENCE_BUDGET,
        )
        if reference:
            parts.append(reference)

    if should_auto_skill(classification) and skills:
        selected = select_skill(skills, classification.primary)
        block = as_prompt_block(
            selected,
            budget=AUTO_SKILL_BUDGET,
        )
        if block:
            parts.append(block)

    return "\n\n".join(parts)
