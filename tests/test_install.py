"""Kurulum yöntemi tespiti, PATH denetimi ve güncelleme/kaldırma komutları.

Hepsi SAF: gerçek kurulum yapılmaz, yol ve ortam metinleri parametre olarak
verilir. Böylece Windows davranışı macOS'ta, macOS davranışı Linux'ta test edilir.
"""

from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath

import pytest

from fusion_cli.install import (
    InstallMethod,
    detect_method,
    path_hint,
    uninstall_command,
    update_command,
)

# --- Kurulum yöntemi tespiti ------------------------------------------------- #


@pytest.mark.parametrize(
    ("yol", "beklenen"),
    [
        ("/Users/x/.local/share/uv/tools/fusion-cli/bin/python", InstallMethod.UV),
        ("/home/x/.local/pipx/venvs/fusion-cli/bin/python", InstallMethod.PIPX),
        ("/home/x/projeler/fusion-cli/.venv/bin/python", InstallMethod.VENV),
        ("/usr/bin/python3", InstallMethod.UNKNOWN),
    ],
)
def test_yontem_yoldan_tespit_edilir(yol, beklenen):
    """Güncelleme/kaldırma komutu yönteme göre değişir; yanlış komut vermek
    kullanıcıyı çalışmayan bir talimata yollar."""
    assert detect_method(PurePosixPath(yol)) is beklenen


def test_windows_yollari_da_taninir():
    uv = PureWindowsPath(r"C:\Users\x\AppData\Roaming\uv\tools\fusion-cli\Scripts\python.exe")
    pipx = PureWindowsPath(r"C:\Users\x\pipx\venvs\fusion-cli\Scripts\python.exe")

    assert detect_method(uv) is InstallMethod.UV
    assert detect_method(pipx) is InstallMethod.PIPX


# --- Güncelleme ve kaldırma -------------------------------------------------- #


@pytest.mark.parametrize(
    ("yontem", "parca"),
    [
        (InstallMethod.UV, "uv tool upgrade"),
        (InstallMethod.PIPX, "pipx upgrade"),
        (InstallMethod.VENV, "git pull"),
    ],
)
def test_guncelleme_komutu_yonteme_gore_uretilir(yontem, parca):
    assert parca in update_command(yontem)


@pytest.mark.parametrize(
    ("yontem", "parca"),
    [
        (InstallMethod.UV, "uv tool uninstall"),
        (InstallMethod.PIPX, "pipx uninstall"),
    ],
)
def test_kaldirma_komutu_yonteme_gore_uretilir(yontem, parca):
    assert parca in uninstall_command(yontem)


def test_bilinmeyen_yontemde_durust_davranilir():
    """Uydurma komut vermektense bilinmediğini söylemek doğrudur."""
    assert "bilinmiyor" in update_command(InstallMethod.UNKNOWN).lower()
    assert "bilinmiyor" in uninstall_command(InstallMethod.UNKNOWN).lower()


# --- PATH denetimi ----------------------------------------------------------- #


def test_bin_dizini_pathteyse_uyari_yok():
    ipucu = path_hint(
        bin_dir=PurePosixPath("/home/x/.local/bin"),
        path_value="/usr/bin:/home/x/.local/bin",
        shell="/bin/zsh",
        windows=False,
    )

    assert ipucu is None


def test_bin_dizini_pathte_degilse_kabuga_uygun_komut_verilir():
    """Kullanıcının shell'ine uymayan komut vermek sessizce işe yaramaz."""
    ipucu = path_hint(
        bin_dir=PurePosixPath("/home/x/.local/bin"),
        path_value="/usr/bin",
        shell="/bin/zsh",
        windows=False,
    )

    assert ipucu is not None
    assert ".zshrc" in ipucu
    assert "/home/x/.local/bin" in ipucu


def test_fish_kabugu_kendi_sozdizimini_alir():
    ipucu = path_hint(
        bin_dir=PurePosixPath("/home/x/.local/bin"),
        path_value="/usr/bin",
        shell="/usr/bin/fish",
        windows=False,
    )

    assert ipucu is not None
    assert "fish_add_path" in ipucu


def test_windowsta_powershell_komutu_verilir():
    ipucu = path_hint(
        bin_dir=PureWindowsPath(r"C:\Users\x\AppData\Roaming\Python\Scripts"),
        path_value=r"C:\Windows\System32",
        shell="",
        windows=True,
    )

    assert ipucu is not None
    assert "SetEnvironmentVariable" in ipucu  # setx değil (E1-34)


def test_path_karsilastirmasi_windowsta_buyuk_kucuk_harf_duyarsizdir():
    """Windows yolları büyük/küçük harf duyarsızdır; duyarlı karşılaştırma
    kullanıcıya gereksiz uyarı gösterirdi."""
    ipucu = path_hint(
        bin_dir=PureWindowsPath(r"C:\Users\X\Scripts"),
        path_value=r"c:\users\x\scripts;C:\Windows",
        shell="",
        windows=True,
    )

    assert ipucu is None


def test_ipucu_kullanicinin_dosyasini_degistirmez(tmp_path):
    """Bu fonksiyon YALNIZCA metin üretir; shell yapılandırmasına dokunmaz."""
    onceki = sorted(p.name for p in tmp_path.iterdir())

    path_hint(
        bin_dir=PurePosixPath("/home/x/.local/bin"),
        path_value="/usr/bin",
        shell="/bin/bash",
        windows=False,
    )

    assert sorted(p.name for p in tmp_path.iterdir()) == onceki


# --- fusion update / uninstall ----------------------------------------------- #


def test_uninstall_purge_olmadan_config_ve_bellegi_korur(tmp_path, monkeypatch):
    """Kullanıcının anahtarları ve öğrendiği dersler kaldırmayla SİLİNMEZ.

    Aracı kaldırmak "verilerimi de sil" demek değildir; kullanıcı yeniden
    kurduğunda anahtarlarını tekrar girmek zorunda kalmamalı.
    """
    from fusion_cli.cli import maintenance

    config_dir = tmp_path / "config"
    memory = tmp_path / "memory"
    for yol in (config_dir, memory):
        yol.mkdir()
        (yol / "dosya").write_text("veri", encoding="utf-8")

    monkeypatch.setattr(maintenance, "user_config_dir", lambda: config_dir)
    monkeypatch.setattr(maintenance, "memory_dir", lambda: memory)

    silinen = maintenance.purge_user_data(dry_run=True)

    assert silinen == (), "purge olmadan hiçbir şey silinmemeli"
    assert (config_dir / "dosya").exists()
    assert (memory / "dosya").exists()


def test_purge_config_ve_bellegi_siler(tmp_path, monkeypatch):
    from fusion_cli.cli import maintenance

    config_dir = tmp_path / "config"
    memory = tmp_path / "memory"
    for yol in (config_dir, memory):
        yol.mkdir()
        (yol / "dosya").write_text("veri", encoding="utf-8")

    monkeypatch.setattr(maintenance, "user_config_dir", lambda: config_dir)
    monkeypatch.setattr(maintenance, "memory_dir", lambda: memory)

    silinen = maintenance.purge_user_data(dry_run=False)

    assert set(silinen) == {config_dir, memory}
    assert not config_dir.exists() and not memory.exists()


def test_purge_olmayan_dizinde_patlamaz(tmp_path, monkeypatch):
    from fusion_cli.cli import maintenance

    monkeypatch.setattr(maintenance, "user_config_dir", lambda: tmp_path / "yok")
    monkeypatch.setattr(maintenance, "memory_dir", lambda: tmp_path / "hic")

    assert maintenance.purge_user_data(dry_run=False) == ()


# --- PATH'i güvenli şekilde kurma -------------------------------------------- #


def test_pathe_ekleme_onay_olmadan_yapilmaz(tmp_path):
    """Kullanıcının shell dosyasına HABERSİZ yazılmaz.

    Onay yoksa dosyaya dokunulmaz; kullanıcı ne olduğunu bilmeden yapılandırması
    değişmemeli.
    """
    from fusion_cli.install import ensure_on_path

    rc = tmp_path / ".zshrc"
    rc.write_text("# mevcut\n", encoding="utf-8")

    sonuc = ensure_on_path(bin_dir=tmp_path / "bin", config_file=rc, approved=False)

    assert sonuc.changed is False
    assert rc.read_text(encoding="utf-8") == "# mevcut\n"


def test_onayliysa_satir_eklenir_ve_bildirilir(tmp_path):
    from fusion_cli.install import ensure_on_path

    rc = tmp_path / ".zshrc"
    rc.write_text("# mevcut\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"

    sonuc = ensure_on_path(bin_dir=bin_dir, config_file=rc, approved=True)

    icerik = rc.read_text(encoding="utf-8")
    assert sonuc.changed is True
    assert sonuc.config_file == rc
    assert str(bin_dir) in icerik
    assert "# mevcut\n" in icerik, "var olan içerik korunmalı"


def test_ekleme_idempotenttir(tmp_path):
    """İkinci çalıştırma aynı satırı TEKRAR eklememeli."""
    from fusion_cli.install import ensure_on_path

    rc = tmp_path / ".bashrc"
    rc.write_text("", encoding="utf-8")
    bin_dir = tmp_path / "bin"

    ensure_on_path(bin_dir=bin_dir, config_file=rc, approved=True)
    ikinci = ensure_on_path(bin_dir=bin_dir, config_file=rc, approved=True)

    assert ikinci.changed is False
    assert rc.read_text(encoding="utf-8").count(str(bin_dir)) == 1


def test_isaretleyici_yazilir_geri_alma_icin(tmp_path):
    """Eklenen satır TANINABİLİR olmalı; kullanıcı neyi sileceğini bilmeli."""
    from fusion_cli.install import FUSION_MARKER, ensure_on_path

    rc = tmp_path / ".zshrc"
    rc.write_text("", encoding="utf-8")

    ensure_on_path(bin_dir=tmp_path / "bin", config_file=rc, approved=True)

    assert FUSION_MARKER in rc.read_text(encoding="utf-8")


def test_olmayan_dosya_olusturulur(tmp_path):
    from fusion_cli.install import ensure_on_path

    rc = tmp_path / ".profile"

    sonuc = ensure_on_path(bin_dir=tmp_path / "bin", config_file=rc, approved=True)

    assert sonuc.changed is True and rc.exists()


def test_yazilamayan_dosyada_patlamaz(tmp_path, yazma_yasagi_kurulabilir):
    """Kurulum, shell dosyası yazılamıyor diye çökmemeli."""
    from fusion_cli.install import ensure_on_path

    rc = tmp_path / "salt-okunur"
    rc.write_text("", encoding="utf-8")
    rc.chmod(0o400)

    sonuc = ensure_on_path(bin_dir=tmp_path / "bin", config_file=rc, approved=True)

    assert sonuc.changed is False
    assert sonuc.error, "başarısızlık sebebi bildirilmeli"
    rc.chmod(0o600)


# --- Dalga 4: purge onayı ve başarısız silme raporu (L1-10) ------------------- #


def _purge_ortami(tmp_path, monkeypatch):
    from fusion_cli.cli import maintenance

    config_dir = tmp_path / "config"
    memory = tmp_path / "memory"
    for yol in (config_dir, memory):
        yol.mkdir()
        (yol / "dosya").write_text("veri", encoding="utf-8")
    monkeypatch.setattr(maintenance, "user_config_dir", lambda: config_dir)
    monkeypatch.setattr(maintenance, "memory_dir", lambda: memory)
    return maintenance, config_dir, memory


def test_purge_silinemeyen_dizini_raporlar_sessiz_gecmez(tmp_path, monkeypatch):
    maintenance, config_dir, memory = _purge_ortami(tmp_path, monkeypatch)
    gercek = maintenance.shutil.rmtree

    def _bellegi_silme(yol, *a, **k):
        if yol == memory:
            raise PermissionError("izin yok")
        return gercek(yol, *a, **k)

    monkeypatch.setattr(maintenance.shutil, "rmtree", _bellegi_silme)

    sonuc = maintenance.purge_user_data_report(dry_run=False)

    assert sonuc.removed == (config_dir,)
    assert [yol for yol, _ in sonuc.failed] == [memory]
    assert "izin yok" in sonuc.failed[0][1]


def test_uninstall_purge_onay_vermeyince_hicbir_sey_silmez(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from fusion_cli.cli.app import app

    _, config_dir, memory = _purge_ortami(tmp_path, monkeypatch)

    sonuc = CliRunner().invoke(app, ["uninstall", "--purge"], input="n\n")

    assert sonuc.exit_code == 1
    assert (config_dir / "dosya").exists() and (memory / "dosya").exists()


def test_uninstall_purge_yes_ile_onaysiz_siler(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from fusion_cli.cli.app import app

    _, config_dir, memory = _purge_ortami(tmp_path, monkeypatch)

    sonuc = CliRunner().invoke(app, ["uninstall", "--purge", "--yes"])

    assert sonuc.exit_code == 0
    assert not config_dir.exists() and not memory.exists()


_YEREL_BIN = PurePosixPath("/home/x/.local/bin")

# --- Dalga 4: PATH ekleme / yöntem tespiti / Windows önerisi (E1-34/35/36) --------- #


def test_yontem_tespiti_ust_klasordeki_venv_adina_kanmaz():
    """Ölçüldü (30 Ekim): '/Users/x/venv/bin/python3' ve ayrı geçen uv/tools VENV/UV sayılıyordu."""
    assert detect_method(PurePosixPath("/usr/local/uv/lib/tools/py/bin/python")) is (
        InstallMethod.UNKNOWN
    )
    assert detect_method(PurePosixPath("/Users/x/venv/projem/bin/python")) is InstallMethod.UNKNOWN
    assert detect_method(PurePosixPath("/Users/x/venv/bin/python")) is InstallMethod.VENV


def test_windows_onerisi_setx_kullanmaz_yalniz_kullanici_path_ine_ekler():
    ipucu = path_hint(
        bin_dir=PureWindowsPath(r"C:\Users\x\Scripts"),
        path_value=r"C:\Windows",
        shell="",
        windows=True,
    )

    assert ipucu is not None
    assert "setx" not in ipucu.lower()
    assert 'GetEnvironmentVariable("Path", "User")' in ipucu
    assert r"C:\Users\x\Scripts" in ipucu


def test_yorum_satirindaki_dizin_zaten_ekli_sayilmaz(tmp_path):
    from fusion_cli.install import ensure_on_path

    rc = tmp_path / ".zshrc"
    rc.write_text('# export PATH="/home/x/.local/bin:$PATH"\n', encoding="utf-8")

    sonuc = ensure_on_path(
        bin_dir=PurePosixPath("/home/x/.local/bin"), config_file=rc, approved=True
    )

    assert sonuc.changed is True
    assert rc.read_text(encoding="utf-8").count("/home/x/.local/bin") == 2


def test_daha_uzun_yolun_oneki_zaten_ekli_sayilmaz(tmp_path):
    from fusion_cli.install import ensure_on_path

    rc = tmp_path / ".zshrc"
    rc.write_text('export PATH="/home/x/.local/bin2:$PATH"\n', encoding="utf-8")

    sonuc = ensure_on_path(
        bin_dir=PurePosixPath("/home/x/.local/bin"), config_file=rc, approved=True
    )

    assert sonuc.changed is True


def test_aktif_satirdaki_tam_dizin_tekrar_eklenmez(tmp_path):
    from fusion_cli.install import ensure_on_path

    rc = tmp_path / ".zshrc"
    rc.write_text('export PATH="/home/x/.local/bin:$PATH"\n', encoding="utf-8")

    sonuc = ensure_on_path(
        bin_dir=PurePosixPath("/home/x/.local/bin"), config_file=rc, approved=True
    )

    assert sonuc.changed is False
