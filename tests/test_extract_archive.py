"""Arşiv açma — indirilen asset paketini kullanılabilir hâle getiren tek yol.

Ölçülmüş kopukluk: `download_file` paketi indiriyor, sistem istemi "arşivse aç"
diyor, `unzip` tanınan komut olmadığı için etkileşimsiz turda reddediliyordu ve
oyun assetsiz kalıyordu.
"""

from __future__ import annotations

import tarfile
import zipfile

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import archive, build_registry


def _zip_yaz(yol, girisler: dict[str, bytes]) -> None:
    with zipfile.ZipFile(yol, "w") as arsiv:
        for ad, veri in girisler.items():
            arsiv.writestr(ad, veri)


async def test_zip_icindeki_dosyalar_proje_icine_acilir(tmp_path):
    _zip_yaz(tmp_path / "paket.zip", {"sprites/player.png": b"\x89PNG", "readme.txt": b"lisans"})
    context = ToolContext(root=tmp_path)

    sonuc = await archive.extract_archive({"path": "paket.zip", "dest": "assets"}, context)

    assert sonuc.ok
    assert (tmp_path / "assets/sprites/player.png").read_bytes() == b"\x89PNG"
    assert "Dosya: 2" in sonuc.output


async def test_acilan_dosya_edinimdir_geri_almada_silinmez(tmp_path):
    """Adım doğrulaması düşse bile paket yeniden indirilip açılmamalı."""
    _zip_yaz(tmp_path / "paket.zip", {"sprites/player.png": b"\x89PNG"})
    context = ToolContext(root=tmp_path)

    await archive.extract_archive({"path": "paket.zip"}, context)
    geri_alinan = context.changes.restore()

    assert (tmp_path / "sprites/player.png").exists()
    assert geri_alinan == ()


async def test_dest_verilmezse_arsivin_dizinine_acar(tmp_path):
    (tmp_path / "indirilen").mkdir()
    _zip_yaz(tmp_path / "indirilen/paket.zip", {"a.png": b"x"})
    context = ToolContext(root=tmp_path)

    sonuc = await archive.extract_archive({"path": "indirilen/paket.zip"}, context)

    assert sonuc.ok
    assert (tmp_path / "indirilen/a.png").exists()


async def test_yukari_cikan_uye_acilmaz(tmp_path):
    """`../` içeren üye proje dışına yazar; arşiv hiç açılmaz."""
    _zip_yaz(tmp_path / "kotu.zip", {"../kacak.txt": b"zarar"})
    context = ToolContext(root=tmp_path)

    sonuc = await archive.extract_archive({"path": "kotu.zip", "dest": "assets"}, context)

    assert not sonuc.ok
    assert "dışına çıkıyor" in sonuc.output
    assert not (tmp_path / "kacak.txt").exists()


async def test_mutlak_yollu_uye_acilmaz(tmp_path):
    _zip_yaz(tmp_path / "kotu.zip", {"/etc/kacak.txt": b"zarar"})
    context = ToolContext(root=tmp_path)

    sonuc = await archive.extract_archive({"path": "kotu.zip"}, context)

    assert not sonuc.ok
    assert "mutlak yol" in sonuc.output


async def test_sembolik_baglanti_iceren_tar_acilmaz(tmp_path):
    """Bağlantı, hedefi arşivin dışını gösterebilir; açmak sınırı dolaylı aşar."""
    yol = tmp_path / "baglantili.tar"
    with tarfile.open(yol, "w") as arsiv:
        bilgi = tarfile.TarInfo("link")
        bilgi.type = tarfile.SYMTYPE
        bilgi.linkname = "/etc/passwd"
        arsiv.addfile(bilgi)
    context = ToolContext(root=tmp_path)

    sonuc = await archive.extract_archive({"path": "baglantili.tar", "dest": "assets"}, context)

    assert not sonuc.ok
    assert "bağlantı" in sonuc.output
    assert not (tmp_path / "assets/link").exists()


async def test_cok_fazla_uye_iceren_arsiv_acilmaz(tmp_path, monkeypatch):
    monkeypatch.setattr(archive, "MAX_EXTRACT_MEMBERS", 2)
    _zip_yaz(tmp_path / "bomba.zip", {f"d{i}.txt": b"x" for i in range(3)})
    context = ToolContext(root=tmp_path)

    sonuc = await archive.extract_archive({"path": "bomba.zip"}, context)

    assert not sonuc.ok
    assert "dosya sınırını" in sonuc.output


async def test_acildiginda_siniri_asan_arsiv_acilmaz(tmp_path, monkeypatch):
    """Zip bombası: küçük arşiv, açılınca diski dolduran içerik."""
    monkeypatch.setattr(archive, "MAX_EXTRACT_BYTES", 16)
    _zip_yaz(tmp_path / "bomba.zip", {"buyuk.bin": b"0" * 64})
    context = ToolContext(root=tmp_path)

    sonuc = await archive.extract_archive({"path": "bomba.zip"}, context)

    assert not sonuc.ok
    assert "bayt sınırını" in sonuc.output
    assert not (tmp_path / "buyuk.bin").exists()


async def test_arsiv_olmayan_dosya_anlasilir_hata_verir(tmp_path):
    (tmp_path / "player.png").write_bytes(b"\x89PNG")
    context = ToolContext(root=tmp_path)

    sonuc = await archive.extract_archive({"path": "player.png"}, context)

    assert not sonuc.ok
    assert "ZIP ya da TAR" in sonuc.output


async def test_olmayan_arsiv_bildirilir(tmp_path):
    sonuc = await archive.extract_archive({"path": "yok.zip"}, ToolContext(root=tmp_path))

    assert not sonuc.ok
    assert "bulunamadı" in sonuc.output


async def test_tar_gz_acilir(tmp_path):
    yol = tmp_path / "paket.tar.gz"
    (tmp_path / "kaynak.txt").write_bytes(b"ses")
    with tarfile.open(yol, "w:gz") as arsiv:
        arsiv.add(tmp_path / "kaynak.txt", arcname="audio/jump.wav")
    context = ToolContext(root=tmp_path)

    sonuc = await archive.extract_archive({"path": "paket.tar.gz", "dest": "assets"}, context)

    assert sonuc.ok
    assert (tmp_path / "assets/audio/jump.wav").read_bytes() == b"ses"


def test_arac_modele_sunulur():
    """Araç kayıtlı değilse model onu hiç göremez."""
    adlar = {
        schema["function"]["name"]  # type: ignore[index]
        for schema in build_registry().schemas()
    }

    assert "extract_archive" in adlar
