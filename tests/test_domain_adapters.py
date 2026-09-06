"""Alan adaptörü: "neyin kanıt sayıldığı" alana göre tanımlanır, motor değişmez.

Bugün Godot bilgisi motorun içine gömülü: keşif tablosunda bir satır, sıfır-çıkış
işaretleri başka bir tabloda, tanı ayrıştırıcısı üçüncü yerde. Yeni bir alan
eklemek üç dosyaya dokunmak demek ve hiçbiri diğerinden haberdar değil.

Adaptör bunları TEK sözleşmede toplar: bu proje bu alana mı ait, hangi komut kapı,
hangi çıktı işareti hatayı gizler, kabul için ne gerekir.
"""

from __future__ import annotations

from fusion_cli.engines.agent.domains import adapter_for, godot_adapter


def test_godot_projesi_tanınır(tmp_path):
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")

    adaptor = adapter_for(tmp_path)

    assert adaptor is not None
    assert adaptor.name == "godot"


def test_godot_disi_proje_adaptor_uretmez(tmp_path):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")

    assert adapter_for(tmp_path) is None


def test_godot_kapisi_bassiz_dogrulama_komutudur():
    komutlar = godot_adapter().gate_commands()

    assert komutlar == ("godot --headless --path . --quit",)


def test_godot_sifir_cikisa_ragmen_hata_isaretleri_tanimli():
    isaretler = godot_adapter().zero_exit_failure_markers()

    assert "script error" in isaretler
    assert "parse error" in isaretler


def test_adaptor_kabul_kosullarini_bildirir():
    """Kabul, "proje açıldı" değil "açıldı VE hata basmadı"dır."""
    kosullar = godot_adapter().acceptance_criteria()

    metin = " ".join(kosullar).casefold()
    assert "ana sahne" in metin
    assert "error" in metin  # motorun bastığı hata işaretleri koşula giriyor
