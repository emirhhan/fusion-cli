"""Görev tipine göre deterministik skill enjeksiyonu.

Modelin `find_skill` çağırmasını UMUT ETMEK zayıf bir kaldıraç: ölçüldü, sistem
promptuna eklendikten sonra bile 3 koşunun yalnızca 1'inde çağrıldı. Dersler zaten
tur öncesi otomatik hatırlanıyor; skill'ler için aynı simetri kurulur.

Anahtar kelime araması Türkçe görev ↔ İngilizce skill açıklaması arasında çalışmaz;
bu yüzden sorgu görev metninden değil, sınıflandırıcının ürettiği TÜRDEN üretilir.
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.engines.agent.classify import TaskKind
from fusion_cli.engines.agent.skill_recall import select_skill, skill_query
from fusion_cli.tools.capabilities import Capability


def _skill(name: str, description: str) -> Capability:
    return Capability(name=name, description=description, path=Path("yok.md"), source="global")


def test_website_gorevi_icin_sorgu_uretilir():
    assert skill_query(TaskKind.WEBSITE)


def test_belirsiz_gorev_tipi_icin_sorgu_uretilmez():
    """GENERAL/EXPLORE için hangi uzmanlığın gerektiği bilinmez; tahmin edilmez."""
    assert skill_query(TaskKind.GENERAL) == ""
    assert skill_query(TaskKind.EXPLORE) == ""


def test_turkce_gorevde_dogru_skill_secilir():
    """Görev Türkçe, skill açıklamaları İngilizce; köprüyü görev TÜRÜ kurar."""
    havuz = (
        _skill("frontend-design-direction", "Set a frontend design direction for production UI"),
        _skill("quarkus-patterns", "Quarkus architecture patterns for messaging"),
        _skill("laravel-plugin-discovery", "Discover Laravel plugins for development server"),
    )

    secilen = select_skill(havuz, TaskKind.WEBSITE)

    assert secilen is not None and secilen.name == "frontend-design-direction"


def test_eslesme_yoksa_hicbir_skill_secilmez():
    havuz = (_skill("quarkus-patterns", "Quarkus architecture patterns"),)

    assert select_skill(havuz, TaskKind.WEBSITE) is None


def test_belirsiz_turde_skill_secilmez():
    havuz = (_skill("frontend-design-direction", "frontend design ui"),)

    assert select_skill(havuz, TaskKind.GENERAL) is None


def test_bos_havuz_coktermez():
    assert select_skill((), TaskKind.WEBSITE) is None
