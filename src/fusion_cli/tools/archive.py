"""İndirilen arşivi proje içine GÜVENLİ biçimde açar.

Neden var — ölçülmüş bir kopukluk: `download_file` bir asset paketini (ZIP)
indirebiliyor, sistem istemi modele "arşivse aç" diyor, ama açacak hiçbir yol
yoktu. `run_shell` üzerinden `unzip` tanınan komut olmadığı için onay istiyor ve
etkileşimsiz turda reddediliyordu. Sonuç: indirilen 260 KB'lık Kenney paketi
diskte duruyor, oyun assetsiz kalıyordu.

Kabuğa `unzip`/`tar` eklemek yerine araç yazılır: arşiv açmak, üye yollarının
DENETLENMESİNİ gerektirir. `../` içeren ya da mutlak yollu bir üye, proje dışına
dosya yazar; sembolik bağlantı içeren bir arşiv aynı şeyi dolaylı yapar; aşırı
sıkıştırılmış bir arşiv diski doldurur. Bu denetimleri kabuk komutu yapamaz.
"""

from __future__ import annotations

import shutil
import tarfile
import zipfile
import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import require_str
from .files import display_path, resolve_path, writable_path

#: Açılan içeriğin toplam boyut sınırı (bayt). İndirme sınırının (256 MiB) iki katı
#: tutulur: asset paketleri sıkıştırılmış gelir ve açılınca büyür, ama sınırsız
#: büyüme "zip bombası" ile diski doldurur.
MAX_EXTRACT_BYTES = 512 * 1024 * 1024

#: Açılan en fazla dosya sayısı. Kenney paketleri birkaç yüz dosyadır; on binlerce
#: dosya bir asset paketi değildir.
MAX_EXTRACT_MEMBERS = 5_000


@dataclass(frozen=True, slots=True)
class _Member:
    """Arşiv üyesinin denetlenmiş hâli."""

    hedef: Path
    boyut: int
    dizin_mi: bool


class _ArchiveError(ValueError):
    """Arşiv güvenli biçimde açılamıyor."""


def _macos_artigi_mi(ad: str) -> bool:
    """`__MACOSX/` klasörü ve `._*` kaynak çatalı dosyaları gerçek içerik değildir.

    Ölçüldü (30 Ekim): macOS'ta hazırlanan her ZIP'te bunlar açılıyor, dosya ve
    5000 üye sınırını yiyor, proje ağacını `._foo.png` çöpüyle dolduruyordu.
    """
    parcalar = ad.replace("\\", "/").split("/")
    return "__MACOSX" in parcalar or parcalar[-1].startswith("._")


def _dogrula(ad: str, boyut: int, kok: Path, *, baglanti_mi: bool) -> _Member:
    """Üyeyi denetle ve proje içindeki hedef yolunu döndür."""
    if baglanti_mi:
        # Sembolik/sabit bağlantı, hedefi arşivin DIŞINI gösterebilir; açtıktan
        # sonra oraya yazmak proje sınırını sessizce aşar.
        raise _ArchiveError(f"Arşivde bağlantı (symlink) var, açılmadı: {ad}")
    temiz = ad.replace("\\", "/")
    if temiz.startswith("/") or ":" in temiz.split("/")[0]:
        raise _ArchiveError(f"Arşiv mutlak yol içeriyor, açılmadı: {ad}")
    hedef = (kok / temiz).resolve()
    if hedef != kok and kok not in hedef.parents:
        # `../` ile yukarı çıkan üye proje dışına yazar.
        raise _ArchiveError(f"Arşiv hedef dizinin dışına çıkıyor, açılmadı: {ad}")
    return _Member(hedef=hedef, boyut=max(0, boyut), dizin_mi=temiz.endswith("/"))


def _zip_uyeleri(arsiv: zipfile.ZipFile, kok: Path) -> list[tuple[zipfile.ZipInfo, _Member]]:
    uyeler: list[tuple[zipfile.ZipInfo, _Member]] = []
    toplam = 0
    for bilgi in arsiv.infolist():
        if _macos_artigi_mi(bilgi.filename):
            continue
        # Üst 16 bit Unix kipidir; 0xA000 sembolik bağlantıdır.
        baglanti = (bilgi.external_attr >> 16) & 0xF000 == 0xA000
        uye = _dogrula(bilgi.filename, bilgi.file_size, kok, baglanti_mi=baglanti)
        if uye.dizin_mi or bilgi.is_dir():
            continue
        toplam += uye.boyut
        _siniri_denetle(len(uyeler) + 1, toplam)
        uyeler.append((bilgi, uye))
    return uyeler


def _tar_uyeleri(arsiv: tarfile.TarFile, kok: Path) -> list[tuple[tarfile.TarInfo, _Member]]:
    uyeler: list[tuple[tarfile.TarInfo, _Member]] = []
    toplam = 0
    for bilgi in arsiv.getmembers():
        if bilgi.isdir() or _macos_artigi_mi(bilgi.name):
            continue
        if not (bilgi.isfile() or bilgi.islnk() or bilgi.issym()):
            # Aygıt dosyası, FIFO: bir asset paketinde işi yoktur.
            raise _ArchiveError(f"Arşivde olağandışı üye var, açılmadı: {bilgi.name}")
        uye = _dogrula(bilgi.name, bilgi.size, kok, baglanti_mi=bilgi.islnk() or bilgi.issym())
        toplam += uye.boyut
        _siniri_denetle(len(uyeler) + 1, toplam)
        uyeler.append((bilgi, uye))
    return uyeler


def _siniri_denetle(sayi: int, toplam: int) -> None:
    if sayi > MAX_EXTRACT_MEMBERS:
        raise _ArchiveError(f"Arşiv {MAX_EXTRACT_MEMBERS} dosya sınırını aşıyor.")
    if toplam > MAX_EXTRACT_BYTES:
        raise _ArchiveError(f"Arşiv açıldığında {MAX_EXTRACT_BYTES} bayt sınırını aşıyor.")


def _yazma_izni(uyeler: Sequence[tuple[object, _Member]], context: ToolContext) -> None:
    """Hiçbir üye yazılmadan ÖNCE hepsinin hedefi yazma kapısından geçer.

    Hedef dizin izinli olsa da üyeler Remotion kit'i gibi korunan bir yola düşebilir;
    yarım açılmış arşiv bırakmamak için denetim yazmadan önce yapılır.
    """
    for _bilgi, uye in uyeler:
        writable_path(context, str(uye.hedef))


def _yaz(akis: IO[bytes], uye: _Member, context: ToolContext, yeni: list[Path]) -> None:
    """Üyeyi parça parça yaz (tek üye 512 MiB'ı belleğe almaz).

    Var olan dosyanın üstüne yazılıyorsa ÖNCE geri alma kaydı alınır (ölçüldü,
    30 Ekim: arşiv açma sessizce eziyor, içerik hiçbir yerde kalmıyordu). Yeni
    oluşan dosya `yeni` listesine girer; yarıda hata olursa hepsi silinir.
    """
    uye.hedef.parent.mkdir(parents=True, exist_ok=True)
    if uye.hedef.exists():
        context.changes.record(uye.hedef)
    else:
        yeni.append(uye.hedef)
    with uye.hedef.open("wb") as hedef:
        shutil.copyfileobj(akis, hedef)
    # EDİNİM: içerik arşivden geldi, agent yazmadı. Adım düşse bile silinmez;
    # yeniden indirip açmak ağ, süre ve sağlayıcı kotası harcar.
    if uye.hedef in yeni:
        context.changes.record_acquired(uye.hedef)
    context.touched.add(uye.hedef)


def _kismi_temizle(yeni: list[Path]) -> None:
    """Yarım kalan açılımın bu çağrıda OLUŞTURDUĞU dosyaları sil (var olanlara dokunma)."""
    for yol in yeni:
        yol.unlink(missing_ok=True)


async def extract_archive(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Arşivi aç; kaç dosya ve kaç bayt yazıldığını kanıt olarak döndür."""
    arsiv_yolu = resolve_path(context, require_str(args, "path"))
    hedef_metni = str(args.get("dest") or arsiv_yolu.parent)
    # Yazılan yer `writable_path` kapısından geçer: alt ajanın `write_scope`'u ve
    # Remotion kit koruyucusu `write_file` ile aynı şekilde burada da geçerlidir.
    kok = writable_path(context, hedef_metni).resolve()
    if not arsiv_yolu.is_file():
        return ToolResult.failure(f"Arşiv bulunamadı: {display_path(context, arsiv_yolu)}")

    kok.mkdir(parents=True, exist_ok=True)
    # Tek liste: iki arşiv türü aynı özeti üretir, rapor kodu iki kez yazılmaz.
    acilan: list[_Member] = []
    yeni: list[Path] = []
    try:
        if zipfile.is_zipfile(arsiv_yolu):
            with zipfile.ZipFile(arsiv_yolu) as arsiv:
                uyeler = _zip_uyeleri(arsiv, kok)
                _yazma_izni(uyeler, context)
                for bilgi, uye in uyeler:
                    with arsiv.open(bilgi) as akis:
                        _yaz(akis, uye, context, yeni)
                    acilan.append(uye)
        elif tarfile.is_tarfile(arsiv_yolu):
            with tarfile.open(arsiv_yolu) as arsiv:
                tar_uyeleri = _tar_uyeleri(arsiv, kok)
                _yazma_izni(tar_uyeleri, context)
                for tar_bilgi, uye in tar_uyeleri:
                    akis = arsiv.extractfile(tar_bilgi)
                    if akis is None:
                        continue
                    _yaz(akis, uye, context, yeni)
                    acilan.append(uye)
        else:
            return ToolResult.failure(
                "Bu dosya ZIP ya da TAR arşivi değil. Tek dosya indirdiysen açmaya gerek yok."
            )
    except _ArchiveError as hata:
        _kismi_temizle(yeni)
        return ToolResult.failure(str(hata))
    except (
        OSError,
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
        tarfile.TarError,
        # Şifreli ZIP `RuntimeError`, bilinmeyen sıkıştırma `NotImplementedError`, kesik
        # `.tar.gz` `EOFError`/`zlib.error` fırlatır; hepsi modele okunur hata olmalı.
        RuntimeError,
        NotImplementedError,
        EOFError,
        zlib.error,
    ) as hata:
        _kismi_temizle(yeni)
        return ToolResult.failure(f"Arşiv açılamadı: {hata}")

    if not acilan:
        return ToolResult.failure("Arşivde açılacak dosya yok.")
    yazilan = sum(uye.boyut for uye in acilan)
    ornekler = ", ".join(display_path(context, uye.hedef) for uye in acilan[:5])
    kuyruk = " …" if len(acilan) > 5 else ""
    return ToolResult(
        output=(
            f"Açıldı: {display_path(context, arsiv_yolu)} → {display_path(context, kok)}\n"
            f"Dosya: {len(acilan)}, Boyut: {yazilan} bayt\nÖrnek: {ornekler}{kuyruk}"
        )
    )
