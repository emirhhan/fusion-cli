"""Boş dosya okuması, mevcut yazma ve güncellik kapılarını besler."""

from __future__ import annotations

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import build_registry


async def test_bos_dosyayi_gercek_okuma_sonrasi_yazma_basarili(tmp_path):
    target = tmp_path / "bos.txt"
    target.write_bytes(b"")
    context = ToolContext(root=tmp_path)
    registry = build_registry()

    read = await registry.execute("read_file", {"path": "bos.txt"}, context)
    written = await registry.execute(
        "write_file", {"path": "bos.txt", "content": "yeni içerik\n"}, context
    )

    assert read.ok and read.output == "(boş dosya)"
    assert written.ok, written.output
    assert target.read_text(encoding="utf-8") == "yeni içerik\n"
    assert target.resolve() in context.fully_read
    assert context.changes.was_created_this_turn(target.resolve()) is False


async def test_bos_okumadan_sonraki_dis_degisiklik_bayat_yazmayi_reddeder(tmp_path):
    target = tmp_path / "bos.txt"
    target.write_bytes(b"")
    context = ToolContext(root=tmp_path)
    registry = build_registry()
    read = await registry.execute("read_file", {"path": "bos.txt"}, context)
    target.write_text("kullanıcının eklediği\n", encoding="utf-8")

    written = await registry.execute(
        "write_file", {"path": "bos.txt", "content": "ajanın içeriği\n"}, context
    )

    assert read.ok
    assert not written.ok and "okuduktan sonra değişti" in written.output
    assert target.read_text(encoding="utf-8") == "kullanıcının eklediği\n"
    assert not context.touched


async def test_okunmamis_bos_dosyanin_uzerine_yazma_hala_reddedilir(tmp_path):
    target = tmp_path / "bos.txt"
    target.write_bytes(b"")
    context = ToolContext(root=tmp_path)

    written = await build_registry().execute(
        "write_file", {"path": "bos.txt", "content": "yeni\n"}, context
    )

    assert not written.ok and "tam içeriğini okumadın" in written.output
    assert target.read_bytes() == b""
    assert not context.fully_read and not context.touched


async def test_bos_dosyayi_okumak_yazma_alanini_genisletmez(tmp_path):
    target = tmp_path / "bos.txt"
    target.write_bytes(b"")
    context = ToolContext(root=tmp_path, write_scope=())
    registry = build_registry()
    read = await registry.execute("read_file", {"path": "bos.txt"}, context)

    written = await registry.execute(
        "write_file", {"path": "bos.txt", "content": "yeni\n"}, context
    )

    assert read.ok and read.output == "(boş dosya)"
    assert not written.ok and "yazma alanı dışında" in written.output
    assert target.read_bytes() == b""
    assert not context.touched
