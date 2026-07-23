"""Keşif, kabuk ve git araçları."""

from __future__ import annotations

import subprocess

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import build_registry


@pytest.fixture
def context(tmp_path):
    return ToolContext(root=tmp_path)


@pytest.fixture
def registry():
    return build_registry()


def _calistir(registry, context, ad, **args):
    return registry.execute(ad, args, context)


def test_search_code_eslesmeleri_dosya_satir_ile_dondurur(registry, context, tmp_path):
    (tmp_path / "a.py").write_text("def merhaba():\n    return 1\n", encoding="utf-8")

    cikti = _calistir(registry, context, "search_code", pattern="def ").output

    assert "a.py:1:" in cikti and "def merhaba" in cikti


def test_search_code_gurultu_dizinlerini_atlar(registry, context, tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text("hedef", encoding="utf-8")
    (tmp_path / "kod.py").write_text("hedef", encoding="utf-8")

    cikti = _calistir(registry, context, "search_code", pattern="hedef").output

    assert "kod.py" in cikti and "node_modules" not in cikti


def test_gecersiz_regex_anlasilir_hata_verir(registry, context):
    sonuc = _calistir(registry, context, "search_code", pattern="[bozuk")

    assert not sonuc.ok and "Geçersiz regex" in sonuc.output


def test_eslesme_yoksa_bilgilendirir(registry, context, tmp_path):
    (tmp_path / "a.py").write_text("bos", encoding="utf-8")

    assert _calistir(registry, context, "search_code", pattern="yok").output == "(eşleşme yok)"


def test_glob_desene_uyan_dosyalari_bulur(registry, context, tmp_path):
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    (tmp_path / "b.txt").write_text("x", encoding="utf-8")
    (tmp_path / "alt").mkdir()
    (tmp_path / "alt" / "c.py").write_text("x", encoding="utf-8")

    cikti = _calistir(registry, context, "glob", pattern="**/*.py").output

    assert "a.py" in cikti and "c.py" in cikti and "b.txt" not in cikti


def test_glob_gurultu_dizinlerini_atlar(registry, context, tmp_path):
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "x.py").write_text("x", encoding="utf-8")

    assert _calistir(registry, context, "glob", pattern="**/*.py").output == "(eşleşen dosya yok)"


def test_run_shell_ciktiyi_ve_cikis_kodunu_dondurur(registry, context):
    sonuc = _calistir(registry, context, "run_shell", command="echo merhaba")

    assert sonuc.ok and "merhaba" in sonuc.output and "çıkış kodu 0" in sonuc.output


def test_run_shell_basarisiz_komutu_isaretler(registry, context):
    sonuc = _calistir(registry, context, "run_shell", command="exit 3")

    assert not sonuc.ok and "çıkış kodu 3" in sonuc.output


def test_run_shell_calisma_dizininde_calisir(registry, context, tmp_path):
    (tmp_path / "isaret.txt").write_text("x", encoding="utf-8")

    cikti = _calistir(registry, context, "run_shell", command="ls").output

    assert "isaret.txt" in cikti


def test_git_yalnizca_salt_okunur_komutlara_izin_verir(registry, context):
    sonuc = _calistir(registry, context, "git", subcommand="push origin main")

    assert not sonuc.ok and "salt-okunur" in sonuc.output


def test_git_status_calisir(registry, context, tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)

    sonuc = _calistir(registry, context, "git", subcommand="status --short")

    assert sonuc.ok


def test_bilinmeyen_arac_kullanilabilir_listeyi_gosterir(registry, context):
    sonuc = registry.execute("olmayan_arac", {}, context)

    assert not sonuc.ok
    assert "Bilinmeyen araç" in sonuc.output and "read_file" in sonuc.output


def test_executor_patlarsa_tur_dusmez(registry, context):
    """Araç sınırı: beklenmedik bir istisna turu düşürmez, modele iletilir."""
    from fusion_cli.core.tools import Tool

    def _patla(args, ctx):
        raise RuntimeError("beklenmedik")

    registry.register(Tool(name="patlayan", description="test", parameters={}, run=_patla))

    sonuc = registry.execute("patlayan", {}, context)

    assert not sonuc.ok
    assert "beklenmedik hata" in sonuc.output and "RuntimeError" in sonuc.output


def test_ayni_ad_iki_kez_kaydedilemez(registry):
    from fusion_cli.core.errors import FusionError
    from fusion_cli.core.tools import Tool

    with pytest.raises(FusionError, match="zaten kayıtlı"):
        registry.register(
            Tool(name="read_file", description="x", parameters={}, run=lambda a, c: None)
        )


def test_takma_adlar_ayni_executoru_kullanir(registry, context, tmp_path):
    (tmp_path / "a.txt").write_text("icerik", encoding="utf-8")

    dogrudan = registry.execute("read_file", {"path": "a.txt"}, context)
    takma = registry.execute("view_file", {"path": "a.txt"}, context)

    assert dogrudan.output == takma.output


def test_semalar_izin_listesiyle_filtrelenir(registry):
    semalar = registry.schemas(allowed={"read_file", "glob"})

    adlar = {sema["function"]["name"] for sema in semalar}
    assert adlar == {"read_file", "glob"}


def test_semalar_function_calling_bicimindedir(registry):
    sema = next(s for s in registry.schemas() if s["function"]["name"] == "edit_file")

    assert sema["type"] == "function"
    assert sema["function"]["parameters"]["required"] == ["path", "old", "new"]
