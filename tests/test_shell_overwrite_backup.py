"""`cp`/`mv`/yönlendirme ile ezilen proje dosyası geri alma kaydına girer (T1-18)."""

from __future__ import annotations

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import build_registry
from fusion_cli.tools.shell_overwrite import backup_paths


@pytest.fixture
def context(tmp_path):
    return ToolContext(root=tmp_path)


async def _kos(context, komut):
    return await build_registry().execute("run_shell", {"command": komut}, context)


def test_cp_hedefi_varsa_hedef_listelenir(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")

    assert backup_paths("cp a.txt b.txt", tmp_path) == [tmp_path / "b.txt"]


def test_hedef_yoksa_bos_doner(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")

    assert backup_paths("cp a.txt yeni.txt", tmp_path) == []


def test_dizine_kopyalamada_dizin_icindeki_ayni_adli_dosya_listelenir(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "dizin").mkdir()
    (tmp_path / "dizin" / "a.txt").write_text("eski", encoding="utf-8")

    assert backup_paths("cp a.txt dizin/", tmp_path) == [tmp_path / "dizin" / "a.txt"]


def test_yonlendirme_ve_tee_hedefleri_listelenir(tmp_path):
    (tmp_path / "x.txt").write_text("x", encoding="utf-8")
    (tmp_path / "y.txt").write_text("y", encoding="utf-8")

    assert backup_paths("echo yeni > x.txt", tmp_path) == [tmp_path / "x.txt"]
    assert backup_paths("echo yeni >> x.txt", tmp_path) == [tmp_path / "x.txt"]
    assert backup_paths("echo yeni | tee y.txt", tmp_path) == [tmp_path / "y.txt"]
    assert backup_paths("echo yeni > /dev/null 2>&1", tmp_path) == []


def test_zincirde_her_parca_taranir(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")

    assert backup_paths("mkdir -p d && mv a.txt b.txt", tmp_path) == [
        tmp_path / "a.txt",
        tmp_path / "b.txt",
    ]


def test_proje_disi_yol_listelenmez(tmp_path):
    assert backup_paths("cp a.txt /etc/hosts", tmp_path) == []


async def test_cp_kaydi_korur_kanitsiz_yazmayi_geri_almaz(context, tmp_path):
    (tmp_path / "a.txt").write_text("yeni", encoding="utf-8")
    (tmp_path / "b.txt").write_text("kullanicinin", encoding="utf-8")

    sonuc = await _kos(context, "cp a.txt b.txt")

    assert sonuc.ok
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "yeni"
    assert context.changes.restore() == ()
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "yeni"
    assert context.changes.snapshots[0].content == b"kullanicinin"
    assert context.changes.conflicts[0].path == tmp_path / "b.txt"
    assert "yazarı doğrulanamadı" in sonuc.output


async def test_yonlendirme_sahipligi_kanitsizsa_ilk_kayit_korunur(context, tmp_path):
    (tmp_path / "notlar.txt").write_text("onemli", encoding="utf-8")

    await _kos(context, "echo x > notlar.txt")

    assert (tmp_path / "notlar.txt").read_text(encoding="utf-8").strip() == "x"
    assert context.changes.restore() == ()
    assert (tmp_path / "notlar.txt").read_text(encoding="utf-8") == "x\n"
    assert context.changes.snapshots[0].content == b"onemli"
    assert context.changes.conflicts[0].path == tmp_path / "notlar.txt"


async def test_mv_kaynagi_ve_hedefi_kanitsizsa_anlik_goruntuleri_kalir(context, tmp_path):
    (tmp_path / "a.txt").write_text("a-icerik", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b-icerik", encoding="utf-8")

    await _kos(context, "mv a.txt b.txt")

    assert not (tmp_path / "a.txt").exists()
    assert context.changes.restore() == ()
    assert not (tmp_path / "a.txt").exists()
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "a-icerik"
    assert {snapshot.path.name: snapshot.content for snapshot in context.changes.snapshots} == {
        "a.txt": b"a-icerik",
        "b.txt": b"b-icerik",
    }
    assert {conflict.path for conflict in context.changes.conflicts} == {
        tmp_path / "a.txt",
        tmp_path / "b.txt",
    }


async def test_hedef_yoksa_kayit_alinmaz(context, tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")

    await _kos(context, "cp a.txt yeni.txt")

    assert not context.changes.paths


@pytest.fixture
def isolated_process(monkeypatch):
    from types import SimpleNamespace

    from fusion_cli.tools import shell

    run = SimpleNamespace(plan=SimpleNamespace(refused="", prefix=()))
    monkeypatch.setattr(shell, "prepare_sandbox", lambda *_: run)
    monkeypatch.setattr(shell, "release_sandbox", lambda *_: None)
    monkeypatch.setattr(shell, "_shell_env", lambda *_: {})
    monkeypatch.setattr(shell, "sandbox_env", lambda *_: {})
    monkeypatch.setattr(shell, "_sandbox_notes", lambda *_: "")
    monkeypatch.setattr(shell, "check_shell_result", lambda _context, result, **_: result)
    return shell


@pytest.mark.parametrize(
    "command,returncode,writer,content",
    [
        ("cp missing.txt target.txt", 1, "user", "kullanici"),
        ("cp missing.txt target.txt || true", 0, "user", "kullanici"),
        ("printf partial > target.txt; false", 1, "process", "kismi-ajan"),
        ("cp source.txt target.txt", 0, "process", "kaynak"),
    ],
)
def test_shell_farki_yazan_sahipligi_kanitlamaz(
    tmp_path, context, monkeypatch, isolated_process, command, returncode, writer, content
):
    import subprocess

    hedef = tmp_path / "target.txt"
    hedef.write_text("ilk", encoding="utf-8")
    (tmp_path / "source.txt").write_text("kaynak", encoding="utf-8")

    def complete(*args, **kwargs):
        hedef.write_text(content, encoding="utf-8")
        return subprocess.CompletedProcess(command, returncode, "", "")

    monkeypatch.setattr(isolated_process, "run_foreground", complete)

    result = isolated_process.run_shell({"command": command}, context)

    assert result.ok == (returncode == 0)
    assert result.workspace_effect.changed == ("target.txt",)
    assert context.changes.restore() == (), writer
    assert hedef.read_text(encoding="utf-8") == content
    assert context.changes.snapshots[0].content == b"ilk"
    assert context.changes.conflicts[0].path == hedef


@pytest.mark.parametrize("is_changed", [True, False])
def test_shell_kanitsiz_degisimde_onceki_arac_kimligini_gecersiz_kilar(
    tmp_path, context, monkeypatch, isolated_process, is_changed
):
    import os
    import subprocess

    from fusion_cli.tools.files import edit_file

    hedef = tmp_path / "target.txt"
    hedef.write_text("ilk", encoding="utf-8")
    assert edit_file({"path": "target.txt", "old": "ilk", "new": "ajan"}, context).ok
    (tmp_path / "other.txt").write_text("diger", encoding="utf-8")
    command = "cp missing.txt other.txt"

    def complete(*args, **kwargs):
        if is_changed:
            timestamp = hedef.stat().st_mtime_ns + 1_000_000_000
            hedef.write_text("ajan", encoding="utf-8")
            os.utime(hedef, ns=(timestamp, timestamp))
        return subprocess.CompletedProcess(command, 1, "", "")

    monkeypatch.setattr(isolated_process, "run_foreground", complete)
    result = isolated_process.run_shell({"command": command}, context)
    assert not result.ok

    restored = context.changes.restore()

    if is_changed:
        assert restored == ()
        assert hedef.read_text(encoding="utf-8") == "ajan"
        assert context.changes.conflicts[0].path == hedef
        assert context.changes.snapshots[0].content == b"ilk"
    else:
        assert restored == (hedef,)
        assert hedef.read_text(encoding="utf-8") == "ilk"
        assert all(conflict.path != hedef for conflict in context.changes.conflicts)


async def test_gercek_kismi_shell_yazmasi_sahiplik_kaniti_uydurmaz(context, tmp_path):
    hedef = tmp_path / "target.txt"
    hedef.write_text("ilk", encoding="utf-8")

    result = await _kos(context, "printf kismi > target.txt; false")

    assert not result.ok
    assert hedef.read_text(encoding="utf-8") == "kismi"
    assert context.changes.restore() == ()
    assert context.changes.snapshots[0].content == b"ilk"
    assert context.changes.conflicts[0].path == hedef
    assert "yazarı doğrulanamadı" in result.output
