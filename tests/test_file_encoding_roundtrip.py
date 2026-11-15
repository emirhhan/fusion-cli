"""Ajanın dosya araçları satır sonu ve BOM'u korur (WP05).

Ölçüldü (29 Ekim): `read_text` evrensel satır sonu kipinde okuyup yazma `\\n`
yazdığı için CRLF bir dosyada tek kelimelik `edit_file`, BÜTÜN satır sonlarını LF'ye
çeviriyordu. Git her satırı değişmiş gösterir; Windows araçları dosyayı bozuk görür.
Eşleştirme kolaylığı korunur: model `\\n` ile yazar, dosyanın kendi biçimiyle kaydedilir.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools.files import edit_file, multi_edit, read_file, write_file

BOM = "﻿".encode()


def _ctx(root: Path) -> ToolContext:
    return ToolContext(root=root)


@pytest.mark.parametrize("bom", [b"", BOM])
def test_crlf_dosyada_duzenleme_satir_sonlarini_ve_bomu_korur(tmp_path, bom):
    (tmp_path / "a.txt").write_bytes(bom + "bir\r\niki\r\nüç\r\n".encode())

    sonuc = edit_file({"path": "a.txt", "old": "iki\nüç", "new": "IKI\nÜÇ"}, _ctx(tmp_path))

    assert sonuc.ok, sonuc.output
    assert (tmp_path / "a.txt").read_bytes() == bom + "bir\r\nIKI\r\nÜÇ\r\n".encode()


def test_multi_edit_crlf_korur(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"a\r\nb\r\nc\r\n")

    sonuc = multi_edit(
        {"path": "a.txt", "edits": [{"old": "a", "new": "A"}, {"old": "c", "new": "C"}]},
        _ctx(tmp_path),
    )

    assert sonuc.ok, sonuc.output
    assert (tmp_path / "a.txt").read_bytes() == b"A\r\nb\r\nC\r\n"


def test_tam_yazim_var_olan_dosyanin_satir_sonu_bicimini_korur(tmp_path):
    (tmp_path / "b.txt").write_bytes(b"x\r\ny\r\n")
    context = _ctx(tmp_path)
    read_file({"path": "b.txt"}, context)

    sonuc = write_file({"path": "b.txt", "content": "x\ny\nz\n"}, context)

    assert sonuc.ok, sonuc.output
    assert (tmp_path / "b.txt").read_bytes() == b"x\r\ny\r\nz\r\n"


def test_lf_dosya_ve_yeni_dosya_lf_kalir(tmp_path):
    (tmp_path / "c.txt").write_bytes(b"a\nb\n")

    edit_file({"path": "c.txt", "old": "a", "new": "A"}, _ctx(tmp_path))
    write_file({"path": "yeni.txt", "content": "x\ny\n"}, _ctx(tmp_path))

    assert (tmp_path / "c.txt").read_bytes() == b"A\nb\n"
    assert (tmp_path / "yeni.txt").read_bytes() == b"x\ny\n"
