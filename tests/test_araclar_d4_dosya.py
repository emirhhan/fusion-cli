"""Dosya araçları P2/P3 düzeltmeleri (T1-23..T1-29, T1-66)."""

from __future__ import annotations

import os
import threading

import pytest

from fusion_cli.core.constants import MAX_DIR_ENTRIES
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import files
from fusion_cli.tools.args import require_positive_int


@pytest.fixture
def context(tmp_path):
    return ToolContext(root=tmp_path)


def test_fifo_okunmaz_asilmaz(context, tmp_path):
    """T1-25: FIFO/aygıt dosyası `read_bytes()` ile sonsuza dek bloklar; düzenli dosya şart."""
    fifo = tmp_path / "boru"
    os.mkfifo(fifo)
    sonuclar: list = []
    # Eski kodda `read_bytes()` FIFO'da sonsuza dek bloklar; test da takılmasın.
    kosu = threading.Thread(
        target=lambda: sonuclar.append(files.read_file({"path": "boru"}, context)), daemon=True
    )
    kosu.start()
    kosu.join(5)

    assert sonuclar, "read_file FIFO'da bloklandı"
    assert not sonuclar[0].ok and "düzenli dosya" in sonuclar[0].output


def test_replace_all_metin_true_kabul_edilir(context, tmp_path):
    """T1-27: zayıf model bool'u "true" metni olarak yollar; sessizce False sayılmamalı."""
    hedef = tmp_path / "a.txt"
    hedef.write_text("x x x\n", encoding="utf-8")

    sonuc = files.edit_file(
        {"path": "a.txt", "old": "x", "new": "y", "replace_all": "true"}, context
    )

    assert sonuc.ok
    assert hedef.read_text(encoding="utf-8") == "y y y\n"


def test_multi_edit_replace_all_metin_true_kabul_edilir(context, tmp_path):
    hedef = tmp_path / "a.txt"
    hedef.write_text("x x\n", encoding="utf-8")

    sonuc = files.multi_edit(
        {"path": "a.txt", "edits": [{"old": "x", "new": "y", "replace_all": "true"}]}, context
    )

    assert sonuc.ok
    assert hedef.read_text(encoding="utf-8") == "y y\n"


def test_edit_file_utf8_olmayan_dosyada_anlasilir_hata(context, tmp_path):
    """T1-24: ham UnicodeDecodeError yerine modele yol gösteren hata."""
    hedef = tmp_path / "eski.txt"
    hedef.write_bytes("şğü".encode("cp1254"))

    sonuc = files.edit_file({"path": "eski.txt", "old": "a", "new": "b"}, context)
    cok = files.multi_edit({"path": "eski.txt", "edits": [{"old": "a", "new": "b"}]}, context)

    assert not sonuc.ok and "UTF-8" in sonuc.output
    assert not cok.ok and "UTF-8" in cok.output


def test_list_dir_gizli_dosyalar_kapasiteyi_yemez_ve_kirpma_bildirilir(context, tmp_path):
    """T1-28: dilimleme gizli dosya süzmesinden SONRA; kırpılırsa "+N" notu."""
    for sayi in range(5):
        (tmp_path / f".gizli{sayi}").write_text("", encoding="utf-8")
    for sayi in range(MAX_DIR_ENTRIES + 3):
        (tmp_path / f"dosya{sayi:05d}.txt").write_text("", encoding="utf-8")

    cikti = files.list_dir({}, context).output

    assert cikti.count("📄") == MAX_DIR_ENTRIES
    assert "+3 girdi daha" in cikti


def test_satir_bolme_read_file_ve_buyuk_dosya_yolunda_ayni(context, tmp_path):
    """T1-23: form-feed / U+2028 satır ayırıcı DEĞİLDİR (ripgrep ve editörle aynı sayım)."""
    govde = "a\x0cb\nc d\ne\n"
    hedef = tmp_path / "k.py"
    hedef.write_text(govde, encoding="utf-8")

    cikti = files.read_file({"path": "k.py"}, context).output

    satirlar = [s for s in cikti.split("\n") if s.strip()]
    assert len(satirlar) == 3
    assert satirlar[0].endswith("a\x0cb")


def test_atomik_yazma_symlinki_ezmez(tmp_path):
    """T1-29: symlink hedefi gerçek dosyaya yazılır; bağın kendisi korunur."""
    gercek = tmp_path / "gercek.txt"
    gercek.write_text("eski\n", encoding="utf-8")
    bag = tmp_path / "bag.txt"
    bag.symlink_to(gercek)

    files.atomic_write(bag, "yeni\n")

    assert bag.is_symlink()
    assert gercek.read_text(encoding="utf-8") == "yeni\n"


def test_yarim_python_zaten_engelleniyor(context, tmp_path):
    """T1-26 (.py): `validate_structured` kesik Python'u diske hiç yazmaz (önceden vardı)."""
    sonuc = files.write_file({"path": "m.py", "content": "def f(:\n    return (1 +\n"}, context)

    assert not sonuc.ok and "sözdizimi" in sonuc.output


def test_yarim_css_dengesiz_parantez_uyari_alir(context, tmp_path):
    sonuc = files.write_file({"path": "s.css", "content": "a { color: red;\nb { x: y"}, context)

    assert sonuc.ok and "süslü parantez" in sonuc.output


def test_yarim_html_kapanmayan_uyari_alir(context, tmp_path):
    sonuc = files.write_file(
        {"path": "i.html", "content": "<!doctype html><html><body><div>"}, context
    )

    assert sonuc.ok and "</html>" in sonuc.output


def test_saglam_python_uyari_almaz(context, tmp_path):
    sonuc = files.write_file({"path": "m.py", "content": "x = 1\n"}, context)

    assert sonuc.ok and "UYARI" not in sonuc.output


@pytest.mark.parametrize("ham", [True, float("inf"), "abc", None])
def test_pozitif_int_gecersiz_degerde_varsayilana_duser(ham):
    """T1-66: bool 1 sayılmaz, inf OverflowError fırlatmaz."""
    assert require_positive_int({"limit": ham}, "limit", default=7) == 7
