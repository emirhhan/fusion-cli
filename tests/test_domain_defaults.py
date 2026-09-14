"""Varsayılan alan kaydı ve eski `domains` içe aktarmalarının geriye uyumu.

Godot bilgisi motordan alan paketine taşınırken tek bir davranış değişmemeli: eski
içe aktarma yolları aynı adaptörü vermeli, keşif ve kapı sırası aynı kalmalı.
"""

from __future__ import annotations

import pytest

from fusion_cli.engines.agent.domain_adapters.defaults import default_domain_registry
from fusion_cli.engines.agent.domain_adapters.godot import godot_adapter
from fusion_cli.engines.agent.domain_adapters.web import web_adapter


def test_varsayilan_kayit_godot_ve_web_alanlarini_sirayla_icerir():
    assert tuple(adaptor.name for adaptor in default_domain_registry().adapters) == ("godot", "web")


def test_iki_varsayilan_kayit_esittir():
    """Kayıt değer nesnesidir: ayrı kurulan iki varsayılan örnek ayrışamaz."""
    assert default_domain_registry() == default_domain_registry()


def test_eski_domains_iceri_aktarmalari_ayni_adaptoru_verir():
    from fusion_cli.engines.agent import domains
    from fusion_cli.engines.agent.domain_adapters import godot

    assert domains.godot_adapter() == godot_adapter()
    assert domains.web_adapter() == web_adapter()
    assert domains.godot_has_main_scene is godot.godot_has_main_scene
    assert domains.godot_needs_import is godot.godot_needs_import


def test_godot_ve_web_birlikte_eslesirse_adapter_for_godotu_secer(tmp_path):
    from fusion_cli.engines.agent.domains import adapter_for

    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")

    adaptor = adapter_for(tmp_path)

    assert adaptor is not None
    assert adaptor.name == "godot"


def test_godot_calistirilabilir_adi_isaret_taramasinin_anahtaridir():
    assert godot_adapter().executable == "godot"


@pytest.mark.parametrize(
    ("gorev", "beklenen"),
    [
        ("Godot'ta platform oyunu yap", True),
        ("GDScript hatasını düzelt", True),
        ("main.tscn sahnesine düğüm ekle", True),
        ("godotengine.org sürüm notlarını özetle", False),
        ("tarayıcıda çalışan bir oyun yap", False),
        ("Dead Cells benzeri bir oyun istiyorum", False),
    ],
)
def test_godot_gorev_isaretleri_alt_dizeyle_tetiklenmez(gorev, beklenen):
    assert godot_adapter().is_named_in(gorev) is beklenen


@pytest.mark.parametrize(
    ("gorev", "beklenen"),
    [
        ("basit bir HTML sayfası yap", True),
        ("şirket için web sitesi kur", True),
        ("ürün için landing page tasarla", True),
        ("webhook ekle", False),
        ("XHTML ayrıştırıcısını düzelt", False),
        ("web API'si yaz", False),
    ],
)
def test_web_gorev_isaretleri_alt_dizeyle_tetiklenmez(gorev, beklenen):
    assert web_adapter().is_named_in(gorev) is beklenen
