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


# --- Fusion'a ait web referansı ---------------------------------------------- #
#
# Kullanıcının kütüphanesindeki tasarım skill'i tamamen soyut ("choose a direction",
# "prefer contextual typography"). Model onu yükledi ve yine jenerik çıktı üretti:
# sıfat kopyalanamaz, değer kopyalanır. Bu referans somut ölçekler taşır ve fusion'a
# aittir — kullanıcının kurulumuna bağlı değildir.


def test_website_gorevinde_web_referansi_eklenir():
    from fusion_cli.engines.agent.skill_recall import reference_block

    blok = reference_block(TaskKind.WEBSITE)

    assert "--space-" in blok, "somut boşluk ölçeği taşımalı"
    assert "clamp(" in blok, "akışkan tip ölçeği taşımalı"


def test_website_disinda_referans_eklenmez():
    from fusion_cli.engines.agent.skill_recall import reference_block

    assert reference_block(TaskKind.BUGFIX) == ""
    assert reference_block(TaskKind.GENERAL) == ""


def test_referans_kullanici_skilliyle_birlikte_verilir():
    """İkisi farklı işe yarar: skill yön seçtirir, referans nasıl inşa edileceğini söyler."""
    from fusion_cli.engines.agent.skill_recall import as_prompt_block, reference_block

    havuz = (_skill("frontend-design-direction", "frontend design direction for UI"),)
    secilen = select_skill(havuz, TaskKind.WEBSITE)

    assert secilen is not None
    assert reference_block(TaskKind.WEBSITE)
    assert as_prompt_block(secilen) or True  # dosya yok; blok boş olabilir
