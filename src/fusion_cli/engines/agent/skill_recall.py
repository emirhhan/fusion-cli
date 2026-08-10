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
from .classify import TaskKind

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
#: ise ~23.000 karakter (system.md 8.134 + araç talimatları 13.304 + çerçeve).
#: Geriye kalan pay budur; tavana dayanmamak için üstü değil altı seçilir.
REFERENCE_BUDGET = 6_000


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


def as_prompt_block(skill: Capability | None) -> str:
    """Seçilen skill'i sistem promptuna eklenecek bloğa çevir; yoksa boş metin."""
    if skill is None:
        return ""
    text = load_skill_text(skill.path, budget=INJECT_BUDGET).strip()
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
