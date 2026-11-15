"""İzole çalışma alanı: aynı görevi birden çok kez denemenin ön koşulu.

8. madde (paralel deneme + kanıtla seçim) bir adımı N kez denemeyi ister; bu, her
denemenin BİRBİRİNİ görmeyen bir kopyada çalışmasını gerektirir. Aksi halde ikinci
deneme birincinin yarım bıraktığı dosyaların üstüne yazar ve "hangi aday kazandı"
sorusu anlamsızlaşır.

İzolasyon git'e BAĞLI DEĞİLDİR: proje git olmayabilir, dosyalar untracked olabilir
ve kullanıcının bekleyen değişiklikleri bulunabilir. Git varsa worktree kullanılır
(ucuzdur), yoksa dizin kopyalanır.
"""

from __future__ import annotations

import subprocess

import pytest

from fusion_cli.core.errors import WorkspaceConflictError
from fusion_cli.core.workspace import IsolatedWorkspace, isolate


def _git_repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "kod.py").write_text("deger = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "ilk"],
        cwd=tmp_path,
        check=True,
    )
    return tmp_path


def test_git_olmayan_projede_dizin_kopyalanir(tmp_path):
    (tmp_path / "kod.py").write_text("deger = 1\n", encoding="utf-8")

    with isolate(tmp_path, name="deneme-1") as alan:
        assert isinstance(alan, IsolatedWorkspace)
        assert (alan.root / "kod.py").read_text(encoding="utf-8") == "deger = 1\n"
        (alan.root / "kod.py").write_text("deger = 2\n", encoding="utf-8")

    # Kopyadaki değişiklik ASIL projeye sızmaz: seçim yapılmadan hiçbir aday kazanmaz.
    assert (tmp_path / "kod.py").read_text(encoding="utf-8") == "deger = 1\n"


def test_git_projesinde_bekleyen_degisiklik_adaya_tasinir(tmp_path):
    kok = _git_repo(tmp_path)
    (kok / "kod.py").write_text("bekleyen = True\n", encoding="utf-8")
    (kok / "izlenmeyen.py").write_text("yeni = True\n", encoding="utf-8")

    with isolate(kok, name="deneme-2") as alan:
        assert (alan.root / "kod.py").read_text(encoding="utf-8") == "bekleyen = True\n"
        assert (alan.root / "izlenmeyen.py").read_text(encoding="utf-8") == "yeni = True\n"
        assert alan.root != kok


def test_iki_deneme_birbirini_gormez(tmp_path):
    (tmp_path / "kod.py").write_text("deger = 1\n", encoding="utf-8")

    with isolate(tmp_path, name="a") as birinci, isolate(tmp_path, name="b") as ikinci:
        (birinci.root / "kod.py").write_text("A\n", encoding="utf-8")

        assert (ikinci.root / "kod.py").read_text(encoding="utf-8") == "deger = 1\n"


def test_kazanan_aday_asil_projeye_uygulanir(tmp_path):
    (tmp_path / "kod.py").write_text("deger = 1\n", encoding="utf-8")

    with isolate(tmp_path, name="kazanan") as alan:
        (alan.root / "kod.py").write_text("deger = 2\n", encoding="utf-8")
        (alan.root / "yeni.py").write_text("yeni = True\n", encoding="utf-8")
        degisenler = alan.apply()

    assert (tmp_path / "kod.py").read_text(encoding="utf-8") == "deger = 2\n"
    assert (tmp_path / "yeni.py").is_file()
    assert {yol.name for yol in degisenler} == {"kod.py", "yeni.py"}


def test_kazanan_adayin_sildigi_dosya_asil_projedan_da_silinir(tmp_path):
    (tmp_path / "eski.py").write_text("artik yok\n", encoding="utf-8")

    with isolate(tmp_path, name="silen") as alan:
        (alan.root / "eski.py").unlink()
        degisenler = alan.apply()

    assert not (tmp_path / "eski.py").exists()
    assert tuple(yol.as_posix() for yol in degisenler) == ("eski.py",)


def test_aday_kosarken_degisen_kullanici_dosyasi_ezilmez(tmp_path):
    asil = tmp_path / "kod.py"
    asil.write_text("ilk\n", encoding="utf-8")

    with isolate(tmp_path, name="cakisma") as alan:
        (alan.root / "kod.py").write_text("aday\n", encoding="utf-8")
        asil.write_text("kullanici\n", encoding="utf-8")
        with pytest.raises(WorkspaceConflictError, match=r"kod[.]py"):
            alan.apply()

    assert asil.read_text(encoding="utf-8") == "kullanici\n"


def test_dizin_dosya_tur_degisiminde_kismi_uygulama_yapilmaz(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "a.txt").write_text("ilk\n", encoding="utf-8")

    with isolate(tmp_path, name="tur-degisimi") as alan:
        (alan.root / "config" / "a.txt").unlink()
        (alan.root / "config").rmdir()
        (alan.root / "config").write_text("aday\n", encoding="utf-8")
        with pytest.raises(WorkspaceConflictError, match="dosya/dizin"):
            alan.apply()

    assert (tmp_path / "config" / "a.txt").read_text(encoding="utf-8") == "ilk\n"
    assert not (tmp_path / "config" / "config").exists()


def test_alan_kapaninca_temizlenir(tmp_path):
    (tmp_path / "kod.py").write_text("deger = 1\n", encoding="utf-8")

    with isolate(tmp_path, name="gecici") as alan:
        yol = alan.root

    assert not yol.exists()


def test_kok_disina_giden_sembolik_baglar_kopyalanmaz(tmp_path):
    """Adayın bağ üzerinden asıl (kök dışı) dosyayı değiştirmesi mümkün olmamalı (C1-28)."""
    dis = tmp_path / "dis"
    dis.mkdir()
    (dis / "gizli.txt").write_text("asıl\n", encoding="utf-8")
    proje = tmp_path / "proje"
    proje.mkdir()
    (proje / "kod.py").write_text("x = 1\n", encoding="utf-8")
    (proje / "mutlak").symlink_to(dis)
    (proje / "goreli_disari").symlink_to("../dis")
    (proje / "ic_hedef").symlink_to("kod.py")

    with isolate(proje, name="bag") as alan:
        assert not (alan.root / "mutlak").exists() and not (alan.root / "mutlak").is_symlink()
        assert not (alan.root / "goreli_disari").is_symlink()
        # kök içi göreli bağ korunur
        assert (alan.root / "ic_hedef").is_symlink()
        assert (alan.root / "ic_hedef").read_text(encoding="utf-8") == "x = 1\n"

    assert (dis / "gizli.txt").read_text(encoding="utf-8") == "asıl\n"


def test_terfi_geri_alma_kullanici_degisimini_korur(tmp_path):
    from fusion_cli.core.changeset import ChangeSet

    asil = tmp_path / "kod.py"
    asil.write_text("ilk\n", encoding="utf-8")
    changes = ChangeSet()
    with isolate(tmp_path, name="terfi") as alan:
        (alan.root / "kod.py").write_text("aday\n", encoding="utf-8")
        alan.apply(changes=changes)
        asil.write_text("kullanici\n", encoding="utf-8")

    assert changes.restore() == ()
    assert asil.read_text(encoding="utf-8") == "kullanici\n"
    assert changes.conflicts[0].path == asil


def test_cok_dosyali_terfi_yarida_kalinca_basarili_yazma_geri_alinir(tmp_path, monkeypatch):
    from fusion_cli.core import workspace
    from fusion_cli.core.changeset import ChangeSet

    for ad in ("a.py", "b.py"):
        (tmp_path / ad).write_text("ilk\n", encoding="utf-8")
    copy2 = workspace.shutil.copy2

    def copy_or_fail(source, target):
        if target.name == "b.py":
            raise OSError("ikinci dosya yazilamadi")
        return copy2(source, target)

    changes = ChangeSet()
    with isolate(tmp_path, name="yarim") as alan:
        for ad in ("a.py", "b.py"):
            (alan.root / ad).write_text("aday\n", encoding="utf-8")
        monkeypatch.setattr(workspace.shutil, "copy2", copy_or_fail)
        with pytest.raises(OSError, match="ikinci dosya"):
            alan.apply(changes=changes)

    assert changes.restore() == (tmp_path / "a.py",)
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "ilk\n"
    assert (tmp_path / "b.py").read_text(encoding="utf-8") == "ilk\n"


def test_terfi_olusturma_ve_silme_kaydi_geri_alinabilir(tmp_path):
    from fusion_cli.core.changeset import ChangeSet

    eski = tmp_path / "eski.py"
    yeni = tmp_path / "yeni.py"
    eski.write_text("ilk\n", encoding="utf-8")
    changes = ChangeSet()
    with isolate(tmp_path, name="olustur-sil") as alan:
        (alan.root / "eski.py").unlink()
        (alan.root / "yeni.py").write_text("aday\n", encoding="utf-8")
        alan.apply(changes=changes)
    assert not eski.exists() and yeni.exists()

    assert set(changes.restore()) == {eski, yeni}
    assert eski.read_text(encoding="utf-8") == "ilk\n"
    assert not yeni.exists() and not changes.conflicts
