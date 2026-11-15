"""Düzenleme güvenilirliği: esnek eşleşme ve düzenleme sonrası sözdizimi kontrolü.

Ölçüldü (30 Ekim): tam eşleşme arayan `edit_file`, model satır sonu boşluğunu ya da
girintiyi kaybedince "bulunamadı" deyip turu yakıyordu; Aider'ın ölçümünde esnek
eşleşme bu sınıf hatayı ~9 kat azalttı. Sözdizimi hatası ise ancak sonraki turda
çalıştırınca görülüyordu.
"""

from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import files, sozdizimi_kontrol
from fusion_cli.tools.esnek_eslesme import apply_flexible


@pytest.fixture
def context(tmp_path: Path) -> ToolContext:
    return ToolContext(root=tmp_path)


def _yaz(tmp_path: Path, ad: str, icerik: str) -> Path:
    yol = tmp_path / ad
    yol.write_bytes(icerik.encode("utf-8"))
    return yol


# --------------------------------------------------------------------------- #
# (a) Esnek eşleşme
# --------------------------------------------------------------------------- #


def test_satir_sonu_bosluguna_takilan_old_uygulanir(tmp_path, context):
    yol = _yaz(tmp_path, "a.txt", "bir   \nx = 1   \niki\n")
    sonuc = files.edit_file({"path": "a.txt", "old": "x = 1\n", "new": "x = 2\n"}, context)
    assert sonuc.ok, sonuc.output
    assert yol.read_text(encoding="utf-8") == "bir   \nx = 2\niki\n"
    assert "esnek_eslesme: true" in sonuc.output
    assert "satır sonu boşluğu" in sonuc.output and "satır 2" in sonuc.output
    assert sonuc.structured and sonuc.structured["esnek_eslesme"] is True


def test_ortak_girinti_kaymasi_tolere_edilir_ve_new_uyarlanir(tmp_path, context):
    yol = _yaz(
        tmp_path,
        "m.py",
        "class A:\n    def f(self):\n        if x:\n            return 1\n        return 2\n",
    )
    # Model satırları girintisiz yolladı (göreli girinti korunmuş).
    sonuc = files.edit_file(
        {
            "path": "m.py",
            "old": "if x:\n    return 1\nreturn 2",
            "new": "if x:\n    return 10\nreturn 20",
        },
        context,
    )
    assert sonuc.ok, sonuc.output
    assert yol.read_text(encoding="utf-8") == (
        "class A:\n    def f(self):\n        if x:\n            return 10\n        return 20\n"
    )
    assert "girinti" in sonuc.output and "satır 3-5" in sonuc.output


def test_sekme_ve_bosluk_farki_dosyanin_stilinde_yazilir(tmp_path, context):
    yol = _yaz(tmp_path, "t.go", "func f() {\n\tif a {\n\t\tb()\n\t}\n}\n")
    sonuc = files.edit_file(
        {
            "path": "t.go",
            "old": "    if a {\n        b()\n    }",
            "new": "    if a {\n        b()\n        c()\n    }",
        },
        context,
    )
    assert sonuc.ok, sonuc.output
    assert yol.read_text(encoding="utf-8") == "func f() {\n\tif a {\n\t\tb()\n\t\tc()\n\t}\n}\n"


def test_crlf_li_old_uygulanir(tmp_path, context):
    yol = _yaz(tmp_path, "c.txt", "bir\niki\nüç\n")
    sonuc = files.edit_file({"path": "c.txt", "old": "bir\r\niki", "new": "bir\r\nIKI"}, context)
    assert sonuc.ok, sonuc.output
    assert yol.read_text(encoding="utf-8") == "bir\nIKI\nüç\n"
    assert "CRLF" in sonuc.output


def test_crlf_dosyada_satir_sonu_korunur(tmp_path, context):
    yol = _yaz(tmp_path, "c.txt", "bir  \r\niki\r\n")
    sonuc = files.edit_file({"path": "c.txt", "old": "bir\n", "new": "BİR\n"}, context)
    assert sonuc.ok, sonuc.output
    assert yol.read_bytes() == "BİR\r\niki\r\n".encode()


def test_birden_cok_esnek_eslesme_reddedilir_dosya_degismez(tmp_path, context):
    icerik = "x = 1  \ny\nx = 1\t\nz\n"
    yol = _yaz(tmp_path, "a.txt", icerik)
    sonuc = files.edit_file({"path": "a.txt", "old": "x = 1", "new": "x = 2"}, context)
    # "x = 1" alt dizgi olarak 2 kez geçer: belirsizlik her zaman reddedilir.
    assert not sonuc.ok
    assert yol.read_text(encoding="utf-8") == icerik


def test_satir_bloklari_birden_cok_yerde_esnek_eslesirse_reddedilir(tmp_path, context):
    icerik = "a  \nb\nara\na\nb  \n"
    yol = _yaz(tmp_path, "a.txt", icerik)
    sonuc = files.edit_file({"path": "a.txt", "old": "a\nb\n", "new": "A\nB\n"}, context)
    assert not sonuc.ok
    assert yol.read_text(encoding="utf-8") == icerik


def test_hic_eslesme_yoksa_bugunku_teshis_mesaji_gelir(tmp_path, context):
    yol = _yaz(tmp_path, "a.txt", "bir\niki\n")
    sonuc = files.edit_file({"path": "a.txt", "old": "olmayan", "new": "x"}, context)
    assert not sonuc.ok and "bulunamadı" in sonuc.output
    assert yol.read_text(encoding="utf-8") == "bir\niki\n"


def test_goreli_girinti_bozulmussa_eslesme_reddedilir(tmp_path, context):
    icerik = "if x:\n    a()\nb()\n"
    yol = _yaz(tmp_path, "a.py", icerik)
    # Düzleşmiş girinti başka bir kod demektir.
    sonuc = files.edit_file({"path": "a.py", "old": "if x:\na()\nb()", "new": "pass"}, context)
    assert not sonuc.ok
    assert yol.read_text(encoding="utf-8") == icerik


def test_replace_all_ile_esnek_yol_calismaz(tmp_path, context):
    icerik = "x = 1  \nx = 1  \n"
    yol = _yaz(tmp_path, "a.txt", icerik)
    sonuc = files.edit_file(
        {"path": "a.txt", "old": "x = 1\n", "new": "x = 2\n", "replace_all": True}, context
    )
    assert not sonuc.ok
    assert yol.read_text(encoding="utf-8") == icerik


def test_ayar_kapaliyken_esnek_yol_calismaz(tmp_path, context):
    kapali = replace(context, edit_fuzzy_match=False)
    icerik = "x = 1   \n"
    yol = _yaz(tmp_path, "a.txt", icerik)
    sonuc = files.edit_file({"path": "a.txt", "old": "x = 1\n", "new": "x = 2\n"}, kapali)
    assert not sonuc.ok
    assert yol.read_text(encoding="utf-8") == icerik


def test_tam_eslesme_esnek_sayilmaz(tmp_path, context):
    _yaz(tmp_path, "a.txt", "x = 1\n")
    sonuc = files.edit_file({"path": "a.txt", "old": "x = 1", "new": "x = 2"}, context)
    assert sonuc.ok
    assert "esnek_eslesme" not in sonuc.output
    assert not sonuc.structured


def test_multi_edit_esnek_adim_atomik_ve_raporlanir(tmp_path, context):
    yol = _yaz(tmp_path, "a.txt", "bir  \niki\nüç\n")
    sonuc = files.multi_edit(
        {
            "path": "a.txt",
            "edits": [{"old": "bir\n", "new": "BİR\n"}, {"old": "üç", "new": "ÜÇ"}],
        },
        context,
    )
    assert sonuc.ok, sonuc.output
    assert yol.read_text(encoding="utf-8") == "BİR\niki\nÜÇ\n"
    assert "esnek_eslesme: true" in sonuc.output and "1. düzenleme" in sonuc.output
    assert sonuc.structured and sonuc.structured["esnek_duzenleme_sayisi"] == 1


def test_multi_edit_ikinci_duzenleme_belirsizse_dosya_degismez(tmp_path, context):
    icerik = "bir  \niki\nx\nx\n"
    yol = _yaz(tmp_path, "a.txt", icerik)
    sonuc = files.multi_edit(
        {
            "path": "a.txt",
            "edits": [{"old": "bir\n", "new": "BİR\n"}, {"old": "x", "new": "y"}],
        },
        context,
    )
    assert not sonuc.ok and "2. düzenleme" in sonuc.output
    assert yol.read_text(encoding="utf-8") == icerik


def test_apply_flexible_sondaki_newline_dengesizse_none():
    assert apply_flexible("a  \nb\n", "a\n", "A") is None


# --------------------------------------------------------------------------- #
# (b) Düzenleme sonrası sözdizimi kontrolü
# --------------------------------------------------------------------------- #

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node yok")
needs_php = pytest.mark.skipif(shutil.which("php") is None, reason="php yok")


@needs_node
def test_js_sozdizimi_hatasi_yazilir_ama_sonuca_eklenir(tmp_path, context):
    yol = _yaz(tmp_path, "a.js", "const a = 1;\nconst b = 2;\n")
    sonuc = files.edit_file({"path": "a.js", "old": "const b = 2;", "new": "const b = ;"}, context)
    assert sonuc.ok
    assert yol.read_text(encoding="utf-8") == "const a = 1;\nconst b = ;\n"
    assert "sözdizimi hatası: satır 2:" in sonuc.output


@needs_node
def test_js_gecerli_kod_uyari_uretmez(tmp_path, context):
    _yaz(tmp_path, "a.js", "const a = 1;\n")
    sonuc = files.edit_file({"path": "a.js", "old": "1", "new": "2"}, context)
    assert sonuc.ok and "sözdizimi" not in sonuc.output


@needs_node
def test_esm_import_iceren_js_yanlis_alarm_vermez(tmp_path, context):
    _yaz(tmp_path, "a.js", 'import fs from "fs";\nexport const a = 1;\n')
    sonuc = files.edit_file({"path": "a.js", "old": "= 1", "new": "= 2"}, context)
    assert sonuc.ok and "sözdizimi" not in sonuc.output


@needs_node
def test_jsx_iceren_js_atlanir(tmp_path, context):
    _yaz(tmp_path, "a.js", "export const A = () => (\n  <div>merhaba</div>\n);\n")
    sonuc = files.edit_file({"path": "a.js", "old": "merhaba", "new": "selam"}, context)
    assert sonuc.ok and "sözdizimi" not in sonuc.output


@needs_node
def test_ayar_kapaliyken_sozdizimi_kontrolu_yapilmaz(tmp_path, context):
    kapali = replace(context, post_edit_syntax_check=False)
    _yaz(tmp_path, "a.js", "const b = 2;\n")
    sonuc = files.edit_file({"path": "a.js", "old": "2", "new": ""}, kapali)
    assert sonuc.ok and "sözdizimi" not in sonuc.output


@needs_php
def test_php_sozdizimi_hatasi_satir_numarasiyla_bildirilir(tmp_path, context):
    _yaz(tmp_path, "a.php", "<?php\n$a = 1;\n")
    sonuc = files.edit_file({"path": "a.php", "old": "$a = 1;", "new": "$a = ;"}, context)
    assert sonuc.ok
    assert "sözdizimi hatası: satır 2:" in sonuc.output


def test_denetleyici_yoksa_sessizce_atlanir(tmp_path, context, monkeypatch):
    monkeypatch.setattr(sozdizimi_kontrol.shutil, "which", lambda *a, **k: None)
    _yaz(tmp_path, "a.js", "const b = 2;\n")
    sonuc = files.edit_file({"path": "a.js", "old": "2", "new": ""}, context)
    assert sonuc.ok and "sözdizimi" not in sonuc.output


def test_ts_icin_tsc_yoksa_atlanir(tmp_path, context, monkeypatch):
    monkeypatch.setattr(sozdizimi_kontrol, "_find_tsc", lambda *a, **k: None)
    _yaz(tmp_path, "a.ts", "const b: number = 2;\n")
    sonuc = files.edit_file({"path": "a.ts", "old": "2", "new": ""}, context)
    assert sonuc.ok and "sözdizimi" not in sonuc.output


def test_tsc_ciktisinda_yalniz_sozdizimi_kodlari_alinir():
    cikti = (
        "a.ts(3,5): error TS2304: Cannot find name 'foo'.\na.ts(7,9): error TS1005: ';' expected.\n"
    )
    assert sozdizimi_kontrol._parse_tsc(cikti) == "sözdizimi hatası: satır 7: ';' expected."


def test_tsc_yalniz_anlamsal_hata_varsa_sorun_yok():
    assert (
        sozdizimi_kontrol._parse_tsc("a.ts(3,5): error TS2304: Cannot find name 'foo'.\n") is None
    )


def test_zaman_asimi_sessizce_atlanir(tmp_path, context, monkeypatch):
    import subprocess

    def asir(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="node", timeout=1)

    monkeypatch.setattr(sozdizimi_kontrol.subprocess, "run", asir)
    _yaz(tmp_path, "a.js", "const b = 2;\n")
    sonuc = files.edit_file({"path": "a.js", "old": "2", "new": ""}, context)
    assert sonuc.ok and "sözdizimi" not in sonuc.output


def test_python_sozdizimi_hatasi_eskisi_gibi_diske_ulasmaz(tmp_path, context):
    # Python zaten yazmadan ÖNCE `validate_structured` ile engellenir; ikinci bir
    # (uyarı düzeyinde) kontrol açılmadı.
    yol = _yaz(tmp_path, "a.py", "x = 1\n")
    sonuc = files.edit_file({"path": "a.py", "old": "x = 1", "new": "x = ("}, context)
    assert not sonuc.ok
    assert yol.read_text(encoding="utf-8") == "x = 1\n"


def test_onizleme_esnek_eslesmenin_aynisini_gosterir(tmp_path, context):
    from fusion_cli.tools.preview import _preview_edit, _preview_multi_edit

    _yaz(tmp_path, "a.txt", "bir  \niki\n")
    onizleme = _preview_edit({"path": "a.txt", "old": "bir\n", "new": "BİR\n"}, context)
    assert "+BİR" in onizleme and "eşleşme yok" not in onizleme
    multi = _preview_multi_edit(
        {"path": "a.txt", "edits": [{"old": "bir\n", "new": "BİR\n"}]}, context
    )
    assert "+BİR" in multi
    kapali = replace(context, edit_fuzzy_match=False)
    assert "eşleşme yok" in _preview_edit({"path": "a.txt", "old": "bir\n", "new": "x\n"}, kapali)


def test_calisma_ayari_baglama_yansir():
    from fusion_cli.config.loader import load_config

    runtime = load_config().runtime
    assert runtime.edit_fuzzy_match is True and runtime.post_edit_syntax_check is True
