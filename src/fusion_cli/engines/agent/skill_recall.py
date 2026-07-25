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


def reference_block(kind: TaskKind) -> str:
    """Görev türüne ait fusion referansı; yoksa boş metin."""
    dosya = _REFERENCES.get(kind)
    if dosya is None:
        return ""
    try:
        return (_PROMPTS / dosya).read_text(encoding="utf-8").strip()
    except OSError:
        # Referans okunamıyorsa tur devam eder; bu bir iyileştirmedir.
        return ""
