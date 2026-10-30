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


async def test_cp_ezilen_dosyayi_geri_alma_kaydina_alir(context, tmp_path):
    (tmp_path / "a.txt").write_text("yeni", encoding="utf-8")
    (tmp_path / "b.txt").write_text("kullanicinin", encoding="utf-8")

    sonuc = await _kos(context, "cp a.txt b.txt")

    assert sonuc.ok
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "yeni"
    context.changes.restore()
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "kullanicinin"


async def test_yonlendirmeyle_sifirlanan_dosya_geri_alinabilir(context, tmp_path):
    (tmp_path / "notlar.txt").write_text("onemli", encoding="utf-8")

    await _kos(context, "echo x > notlar.txt")

    assert (tmp_path / "notlar.txt").read_text(encoding="utf-8").strip() == "x"
    context.changes.restore()
    assert (tmp_path / "notlar.txt").read_text(encoding="utf-8") == "onemli"


async def test_mv_kaynagi_ve_hedefi_geri_alinir(context, tmp_path):
    (tmp_path / "a.txt").write_text("a-icerik", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b-icerik", encoding="utf-8")

    await _kos(context, "mv a.txt b.txt")

    assert not (tmp_path / "a.txt").exists()
    context.changes.restore()
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "a-icerik"
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "b-icerik"


async def test_hedef_yoksa_kayit_alinmaz(context, tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")

    await _kos(context, "cp a.txt yeni.txt")

    assert not context.changes.paths
