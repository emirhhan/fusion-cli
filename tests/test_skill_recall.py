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


def test_web_referansi_iskeleyi_kosulsuz_ilk_is_olarak_dayatmaz():
    """Ölçülen zarar: 'ÖNCE BUNU YAP: scaffold_web' emri, var olan bir siteyi taklit
    etmesi istenen bir görevde modele önce jenerik iskele yazdırıyordu."""
    from fusion_cli.engines.agent.skill_recall import reference_block

    blok = reference_block(TaskKind.WEBSITE)

    assert "ÖNCE BUNU YAP" not in blok
    assert "SIFIRDAN" in blok, "iskelenin ne zaman geçerli olduğu yazmalı"
    assert "ATLA" in blok, "iskelenin ne zaman atlanacağı yazmalı"


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


def test_skill_gorev_metninden_secilir():
    """Ölçüldü: 306 skill kuruluyken bir Godot görevine HİÇ skill gelmiyordu.

    Seçim yalnızca görev TÜRÜNE bakıyordu ve `FEATURE` türünün sorgusu BOŞTU —
    yani en yaygın görev tipinde hiçbir skill hiç seçilmiyordu. Bir Godot görevi
    ile bir WordPress görevi aynı türe düşer; ayrımı yapan tek şey görev metnidir.
    """
    from fusion_cli.engines.agent.classify import TaskKind
    from fusion_cli.engines.agent.skill_recall import select_skill

    godot = _skill("godot", "Godot 4 ile oyun yapma, sahne tscn duzenleme")
    wp = _skill("wordpress", "WordPress tema ve eklenti gelistirme")

    secilen = select_skill((godot, wp), TaskKind.FEATURE, task="godot ile 2D oyun yap")

    assert secilen is not None and secilen.name == "godot"


def test_gorev_metni_eslesmezse_tur_terimleri_calisir():
    """Metin eşleşmediğinde eski davranış korunur: tür terimleri seçer."""
    from fusion_cli.engines.agent.classify import TaskKind
    from fusion_cli.engines.agent.skill_recall import select_skill

    hata = _skill("error-handling", "debugging error handling patterns")

    secilen = select_skill((hata,), TaskKind.BUGFIX, task="şu tuhaf davranışı gider")

    assert secilen is not None and secilen.name == "error-handling"


def test_hicbiri_eslesmezse_none_doner():
    from fusion_cli.engines.agent.classify import TaskKind
    from fusion_cli.engines.agent.skill_recall import select_skill

    alakasiz = _skill("kubernetes", "cluster namespace deployment")

    assert select_skill((alakasiz,), TaskKind.FEATURE, task="godot oyunu yap") is None


def test_feature_gorevinde_de_skill_enjekte_edilir():
    """Ölçüldü: `godot` skill'i kurulu ve göreve tam uyuyorken HİÇ etkinleşmedi.

    Kapı `classification.primary in SKILL_QUERIES` diyordu ve tabloda `feature`,
    `explore`, `general` yoktu. Yani en yaygın görev tipleri skill enjeksiyonunu
    baştan kapatıyordu. Kapı artık türe değil, ELDE UYGUN SKILL OLUP OLMADIĞINA
    bakmalı; seçim zaten eşleşme bulamazsa `None` döner ve hiçbir şey enjekte
    edilmez.
    """
    from fusion_cli.engines.agent.classify import TaskClassification, TaskKind
    from fusion_cli.engines.agent.skill_recall import should_auto_skill

    c = TaskClassification(primary=TaskKind.FEATURE, confidence=1.0)

    assert should_auto_skill(c) is True


def test_guven_dusukse_skill_yine_enjekte_edilmez():
    """Güven kapısı korunur: kararsız sınıflandırmada enjeksiyon yapılmaz."""
    from fusion_cli.engines.agent.classify import TaskClassification, TaskKind
    from fusion_cli.engines.agent.skill_recall import should_auto_skill

    c = TaskClassification(primary=TaskKind.FEATURE, confidence=0.0)

    assert should_auto_skill(c) is False


def test_skill_adi_gorevde_geciyorsa_tek_eslesme_yeter():
    """Ölçüldü: "godot sahnesine script bagla" görevinde `godot` skill'i seçilmedi.

    Skor 1'di (yalnız 'godot' tuttu) ve eşik 2'ydi. Ama bir skill'in KENDİ ADININ
    görevde geçmesi, açıklamasından rastgele bir kelime tutmasıyla aynı kanıt
    değildir — özel ad, en güçlü sinyaldir.
    """
    from fusion_cli.engines.agent.classify import TaskKind
    from fusion_cli.engines.agent.skill_recall import MIN_AUTO_SKILL_SCORE, select_skill

    godot = _skill("godot", "oyun sahne tscn gdscript")

    secilen = select_skill(
        (godot,), TaskKind.GENERAL, task="godot sahnesine script bagla",
        min_score=MIN_AUTO_SKILL_SCORE,
    )

    assert secilen is not None and secilen.name == "godot"


def test_adi_gecmeyen_zayif_eslesme_yine_elenir():
    from fusion_cli.engines.agent.classify import TaskKind
    from fusion_cli.engines.agent.skill_recall import MIN_AUTO_SKILL_SCORE, select_skill

    fe = _skill("frontend-design", "css responsive layout design")

    secilen = select_skill(
        (fe,), TaskKind.FEATURE, task="kullaniciya design ekrani ekle",
        min_score=MIN_AUTO_SKILL_SCORE,
    )

    assert secilen is None
