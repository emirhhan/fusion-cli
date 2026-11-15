"""Görev kümelerinin adla çözülmesi ve taslak kabulü.

İki yerden küme okunur: depoyla gelen `evals/suite/<ad>.yaml` ve kullanıcının kendi
makinesindeki `kume/<ad>.yaml` (taslak kabulü buraya yazar; gerçek konuşmadan türeyen
görevler depoya GİRMEZ). Aynı ad ikisinde de varsa kullanıcınınki kazanır.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import yaml

from evals.loader import load_tasks, task_to_mapping
from evals.tasks import CriterionKind, EvalTask, SuccessCriterion
from evals.taslak_deposu import TaslakDeposu
from fusion_cli.core.atomic_file import atomic_replace_text
from fusion_cli.core.errors import EvalError

_KUME_AD = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
BASLIK = (
    "# `fusion eval kabul` ile eklenen görevler gerçek konuşmadan türer.\n"
    "# Bu dosya kullanıcının makinesinde kalır; depoya ya da başkasına verilmez.\n"
)
SETUP_UYARISI = (
    "Görevin `setup:` bloğu boş: istek proje dosyalarına dayanıyorsa kümeyi bu hâliyle "
    "koşmak anlamlı olmaz; ilgili dosyaları kume dosyasında `setup:` altına ekle."
)


def kume_dosyasi(ad: str, dizin: Path) -> Path:
    """Küme adından dosya yolu (ad dosya adına dönüşür; `../` ile kaçılamaz)."""

    if not _KUME_AD.fullmatch(ad) or ".." in ad:
        raise EvalError(f"geçersiz küme adı: {ad!r} (harf, rakam, '.', '_', '-' kullan)")
    return dizin / f"{ad}.yaml"


def kume_coz(ad: str, *, kullanici_dizini: Path, paketli_dizin: Path) -> Path:
    """Adı bir küme dosyasına çöz: önce kullanıcı kümesi, sonra depodaki küme."""

    adaylar = (kume_dosyasi(ad, kullanici_dizini), kume_dosyasi(ad, paketli_dizin))
    for aday in adaylar:
        if aday.is_file():
            return aday
    mevcut = sorted(
        {yol.stem for dizin in (kullanici_dizini, paketli_dizin) for yol in _yamllar(dizin)}
    )
    raise EvalError(f"küme bulunamadı: {ad!r}. Bilinen kümeler: {', '.join(mevcut) or '(yok)'}")


def kabul_edilen_kimlikler(kullanici_dizini: Path) -> set[str]:
    """Kullanıcı kümelerindeki görev kimlikleri (taslak tekrar önerilmesin diye)."""

    kimlikler: set[str] = set()
    for yol in _yamllar(kullanici_dizini):
        try:
            kimlikler.update(gorev.id for gorev in load_tasks(yol))
        except EvalError:
            continue
    return kimlikler


def olcut_olustur(
    *, komut: str | None = None, anahtar: str | None = None, dosya: str | None = None
) -> SuccessCriterion | None:
    """Kullanıcının verdiği ölçüt seçeneğinden `SuccessCriterion` kur; hiçbiri yoksa `None`."""

    verilen = [
        ad for ad, deger in (("komut", komut), ("anahtar", anahtar), ("dosya", dosya)) if deger
    ]
    if len(verilen) > 1:
        raise EvalError("ölçüt için yalnız birini ver: --komut, --anahtar ya da --dosya")
    if komut:
        return SuccessCriterion(kind=CriterionKind.EXIT_CODE, expected_exit_code=0, command=komut)
    if anahtar:
        return SuccessCriterion(kind=CriterionKind.KEYWORD, keyword=anahtar)
    if dosya:
        return SuccessCriterion(kind=CriterionKind.FILE_CHANGED, expected_path=dosya)
    return None


def taslagi_kabul_et(
    depo: TaslakDeposu, taslak_id: str, kume_yolu: Path, *, olcut: SuccessCriterion | None = None
) -> EvalTask:
    """Taslağı kullanıcı kümesine görev olarak ekle ve taslak dosyasını kaldır.

    Verilen `olcut` taslaktakini geçersiz kılar. Ölçüt hiç yoksa KABUL EDİLMEZ: ölçütsüz
    görev başarıyı ölçemez.
    """

    taslak = depo.oku(taslak_id)
    secilen = olcut or taslak.olcut
    if secilen is None:
        raise EvalError(
            f"{taslak_id} için ölçüt yok ({taslak.olcut_notu}). "
            "Şunlardan birini ver: --komut '<doğrulama komutu>', "
            "--anahtar '<cevapta geçen metin>', --dosya '<değişmesi gereken dosya>'."
        )
    gorev = EvalTask(id=taslak.id, request=taslak.request, criterion=secilen)
    gorev_ekle(kume_yolu, gorev)
    depo.kaldir(taslak_id, reddet=False)
    return gorev


def gorev_ekle(yol: Path, gorev: EvalTask) -> None:
    """Görevi küme dosyasının SONUNA ekle; dosyadaki yorumlar ve elle düzenlemeler korunur.

    Sonuç geçici dosyada `load_tasks` ile doğrulanır; geçersizse asıl dosyaya dokunulmaz.
    """

    kayit = yaml.safe_dump([task_to_mapping(gorev)], allow_unicode=True, sort_keys=False, width=100)
    girintili = "".join(f"  {satir}" for satir in kayit.splitlines(keepends=True))
    if yol.is_file():
        mevcut = yol.read_text(encoding="utf-8")
        if any(onceki.id == gorev.id for onceki in load_tasks(yol)):
            raise EvalError(f"görev zaten kümede: {gorev.id} ({yol.name})")
        yeni = mevcut.rstrip("\n") + "\n" + girintili
    else:
        yeni = f"{BASLIK}tasks:\n{girintili}"
    _dogrula(yeni)
    atomic_replace_text(yol, yeni)


def _dogrula(metin: str) -> None:
    with tempfile.TemporaryDirectory() as gecici:
        dosya = Path(gecici) / "dogrulama.yaml"
        dosya.write_text(metin, encoding="utf-8")
        load_tasks(dosya)


def _yamllar(dizin: Path) -> list[Path]:
    return sorted(dizin.glob("*.yaml")) if dizin.is_dir() else []
