"""Hata → eval görevi taslağı hattı (saf).

Kendini geliştirme döngüsünün ilk halkası: kullanıcının gerçek konuşmasındaki
başarısızlıklar, ölçülebilir bir görev TASLAĞINA dönüşür. Taslak kümeye OTOMATİK
girmez; kullanıcı `fusion eval kabul <id>` der (bkz. `evals/kume.py`).

Girdi, çalışma alanının tur günlüğüdür (`transcripts/<özet>/events.jsonl` satırları:
`UserMessage`, `TurnAnswered`, `TurnOutcome`, `ToolExecuted`…). Taslak üç kanıttan doğar:

- kullanıcının açık düzeltmesi ("hayır, yanlış") ya da geri alma isteği: önceki isteğin
  KENDİSİ görev olur, düzeltme kanıt olarak eklenir;
- aynı isteğin yeniden gönderilmesi: ilk gönderim görev olur;
- `failed`/`partial` biten tur: o turun isteği görev olur (yalnız sağlayıcı arızası
  nedeniyle düşen tur HARİÇ: o prompt hatası değildir).

Modül ağa, diske ve saate dokunmaz; metin maskeleme `taslak_maske`, ölçüt çıkarımı
`taslak_olcut` içindedir.
"""

from __future__ import annotations

import difflib
import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from evals.tasks import SuccessCriterion
from evals.taslak_maske import maskele
from evals.taslak_olcut import olcut_cikar
from fusion_cli.core.trace import FailureKind, summarize_run
from fusion_cli.observability.replay import event_from_payload

#: Bir çalıştırmada üretilecek en çok taslak; yüzlerce taslak kullanıcıyı boğar.
MAKS_TASLAK = 50
#: Görev olacak isteğin en az uzunluğu ("devam", "ok" gibi kısa mesajlar görev değildir).
MIN_ISTEK = 12
#: İki isteğin "aynı istek" sayılması için gereken benzerlik oranı.
TEKRAR_BENZERLIGI = 0.85
#: Tekrar aranırken geriye bakılacak tur sayısı.
TEKRAR_PENCERESI = 3
#: Düzeltme kanıtı olarak taslağa yazılacak metnin uzunluğu.
KANIT_UZUNLUGU = 200
TASLAK_KIMLIK = re.compile(r"tk-[0-9a-f]{10}")

_TR = str.maketrans("İIıŞşĞğÜüÖöÇç", "iiissgguuoocc")
#: Düzeltme kalıpları ASCII'ye indirgenmiş metinde aranır (`sadelestir`).
_DUZELTME = re.compile(
    r"^(?:hayir|yanlis|olmadi|olmamis|bu degil|boyle degil|istedigim bu degil|"
    r"nope|wrong|that'?s (?:not|wrong)|not what i)\b|"
    r"\b(?:yanlis (?:yaptin|olmus|oldu|anladin)|bunu istemedim|istedigim bu degil|"
    r"dogru degil|bozdun|olmamis|olmadi)\b"
)
_GERI_ALMA = re.compile(
    r"\bgeri al(?:sana|ir misin|in|\b)|\beski hal(?:ine|e) getir|\bundo\b|\brevert\b"
)
#: Tek başına "hayır" gibi çok kısa yanıtlar düzeltme değil, cevaptır.
_MIN_DUZELTME = 8


class TaslakKaynagi(StrEnum):
    """Taslağı doğuran kanıtın türü; en güçlüsü başta."""

    DUZELTME = "duzeltme"
    GERI_ALMA = "geri_alma"
    TEKRAR = "tekrar"
    KISMI_TUR = "kismi_tur"
    BASARISIZ_TUR = "basarisiz_tur"


_ONCELIK = {kaynak: sira for sira, kaynak in enumerate(TaslakKaynagi)}


@dataclass(frozen=True, slots=True)
class Taslak:
    """Henüz kümeye girmemiş, kullanıcı onayı bekleyen eval görevi."""

    id: str
    kaynak: TaslakKaynagi
    request: str
    olcut: SuccessCriterion | None
    olcut_notu: str
    kanit: tuple[str, ...]
    olusturma: str


@dataclass
class _Tur:
    """Bir kullanıcı mesajı ve ondan sonra gelen kayıtlar (sonraki mesaja kadar)."""

    metin: str
    zaman: float
    kayitlar: list[Mapping[str, object]] = field(default_factory=list)

    @property
    def durum(self) -> str:
        for kayit in self.kayitlar:
            if kayit.get("event") == "TurnOutcome":
                return str(kayit.get("status", ""))
        return ""

    @property
    def cevap(self) -> str:
        cevap = ""
        for kayit in self.kayitlar:
            if kayit.get("event") == "TurnAnswered" and isinstance(kayit.get("text"), str):
                cevap = str(kayit["text"])
        return cevap


def taslak_uret(
    kayitlar: Sequence[Mapping[str, object]],
    *,
    kok: Path,
    ev: Path | None,
    simdi: float,
    sonra: float | None = None,
    maks: int = MAKS_TASLAK,
) -> tuple[Taslak, ...]:
    """Tur günlüğünden taslak üret.

    `sonra` verilirse yalnız o zamandan SONRAKİ kullanıcı mesajları taslak doğurur
    (haftalık çalıştırma son haftayı tarar). Aynı istekten gelen kanıtlar tek taslakta
    birleşir; kaynağı en güçlü olan kalır.
    """

    olusturma = datetime.fromtimestamp(simdi, tz=UTC).isoformat(timespec="seconds")
    toplanan: dict[str, Taslak] = {}
    for turlar in _oturumlar(kayitlar):
        for taslak in _oturum_taslaklari(turlar, kok=kok, ev=ev, sonra=sonra, olusturma=olusturma):
            eski = toplanan.get(taslak.id)
            toplanan[taslak.id] = taslak if eski is None else _birlestir(eski, taslak)
    return tuple(toplanan.values())[:maks]


def _oturumlar(kayitlar: Sequence[Mapping[str, object]]) -> list[list[_Tur]]:
    """Kayıtları oturuma, oturumu da kullanıcı mesajıyla başlayan turlara böl.

    Ölçüldü (30 Ekim): `TranscriptStore.handle` olayın KENDİ `session_id` alanını yazar ve o
    alan çoğu olayda boştur (`null`); yalnız `UserMessage`/`TurnAnswered` oturum kimliği
    taşır. Kimliği olmayan kayıt, dosya sırasına göre EN SON açılan tura bağlanır. Aynı
    çalışma alanında eşzamanlı iki sekme kimliksiz olayları karıştırabilir; bu bilinen sınırdır.
    """

    oturumlar: dict[str, list[_Tur]] = {}
    son_tur: _Tur | None = None
    for kayit in kayitlar:
        oturum = kayit.get("session_id")
        metin = kayit.get("text")
        if kayit.get("event") == "UserMessage" and isinstance(metin, str):
            zaman = kayit.get("timestamp")
            son_tur = _Tur(
                metin=metin, zaman=float(zaman) if isinstance(zaman, int | float) else 0.0
            )
            oturumlar.setdefault(str(oturum), []).append(son_tur)
            continue
        kimlikli = oturumlar.get(oturum) if isinstance(oturum, str) else None
        hedef = kimlikli[-1] if kimlikli else son_tur
        if hedef is not None:
            hedef.kayitlar.append(kayit)
    return list(oturumlar.values())


def _oturum_taslaklari(
    turlar: list[_Tur], *, kok: Path, ev: Path | None, sonra: float | None, olusturma: str
) -> list[Taslak]:
    bulunan: list[Taslak] = []
    for sira, tur in enumerate(turlar):
        if sonra is not None and tur.zaman <= sonra:
            continue
        onceki = turlar[sira - 1] if sira > 0 else None
        kaynak = _duzeltme_kaynagi(tur, onceki)
        if kaynak is not None and onceki is not None:
            kanit = (f"kullanıcı mesajı: «{_kisa(maskele(tur.metin, kok=kok, ev=ev))}»",)
            bulunan += _uret(kaynak, onceki, kanit, kok=kok, ev=ev, olusturma=olusturma)
            continue
        tekrar = _tekrar_edilen(turlar, sira)
        if tekrar is not None:
            kanit = ("aynı istek yeniden gönderildi",)
            bulunan += _uret(
                TaslakKaynagi.TEKRAR, tekrar, kanit, kok=kok, ev=ev, olusturma=olusturma
            )
            continue
        durum_kaynagi = _tur_kaynagi(tur)
        if durum_kaynagi is not None:
            kanit = (f"tur sonucu: {tur.durum}",)
            bulunan += _uret(durum_kaynagi, tur, kanit, kok=kok, ev=ev, olusturma=olusturma)
    return bulunan


def sadelestir(metin: str) -> str:
    """Türkçe harfleri ASCII'ye indirip küçült; kalıp eşleşmesi tek biçime bakar."""

    return " ".join(metin.translate(_TR).lower().split())


def _duzeltme_kaynagi(tur: _Tur, onceki: _Tur | None) -> TaslakKaynagi | None:
    if onceki is None:
        return None
    # Önceki cevap bir soruyla bittiyse "hayır" iş düzeltmesi değil, soruya cevaptır.
    if onceki.cevap.rstrip().endswith("?"):
        return None
    return _duzeltme_deseni(tur.metin)


def _duzeltme_deseni(metin: str) -> TaslakKaynagi | None:
    """Mesajın kendisi düzeltme/geri alma kalıbı taşıyor mu (bağlamdan bağımsız)."""

    if len(metin.strip()) < _MIN_DUZELTME:
        return None
    sade = sadelestir(metin)
    if _GERI_ALMA.search(sade):
        return TaslakKaynagi.GERI_ALMA
    if _DUZELTME.search(sade):
        return TaslakKaynagi.DUZELTME
    return None


def _tekrar_edilen(turlar: list[_Tur], sira: int) -> _Tur | None:
    """Bu mesaj, yakın geçmişteki bir isteğin tekrarıysa İLK gönderimin turunu döndür."""

    metin = sadelestir(turlar[sira].metin)
    if len(metin) < MIN_ISTEK:
        return None
    for onceki in turlar[max(0, sira - TEKRAR_PENCERESI) : sira]:
        gecmis = sadelestir(onceki.metin)
        if len(gecmis) < MIN_ISTEK:
            continue
        if difflib.SequenceMatcher(None, gecmis, metin).ratio() >= TEKRAR_BENZERLIGI:
            return onceki
    return None


def _tur_kaynagi(tur: _Tur) -> TaslakKaynagi | None:
    if tur.durum not in {"failed", "partial"}:
        return None
    olaylar = [olay for kayit in tur.kayitlar if (olay := event_from_payload(kayit)) is not None]
    # Yalnız sağlayıcı/kota arızasıyla düşen tur istem hatası değildir: ölçüm değil altyapı sorunu.
    if summarize_run(olaylar).failures == (FailureKind.PROVIDER,):
        return None
    return TaslakKaynagi.KISMI_TUR if tur.durum == "partial" else TaslakKaynagi.BASARISIZ_TUR


def _uret(
    kaynak: TaslakKaynagi,
    istek_turu: _Tur,
    kanit: tuple[str, ...],
    *,
    kok: Path,
    ev: Path | None,
    olusturma: str,
) -> list[Taslak]:
    istek = maskele(istek_turu.metin.strip(), kok=kok, ev=ev)
    # Düzeltmenin kendisi olan bir mesaj görev olamaz (zincir: "hayır" → "hayır yine olmadı").
    if len(istek) < MIN_ISTEK or _duzeltme_deseni(istek_turu.metin) is not None:
        return []
    olaylar = [olay for kayit in istek_turu.kayitlar if (olay := event_from_payload(kayit))]
    ozet = summarize_run(olaylar)
    olcut, olcut_notu = olcut_cikar(istek_turu.kayitlar, kok=kok, ev=ev)
    teshis = () if ozet.ok else (f"turun teşhisi: {ozet.headline()}",)
    return [
        Taslak(
            id=taslak_kimligi(istek),
            kaynak=kaynak,
            request=istek,
            olcut=olcut,
            olcut_notu=olcut_notu,
            kanit=(*kanit, *teshis),
            olusturma=olusturma,
        )
    ]


def taslak_kimligi(istek: str) -> str:
    """Maskelenmiş isteğin kararlı kimliği: aynı istek tekrar üretilince aynı id çıkar."""

    ozet = hashlib.sha256(sadelestir(istek).encode()).hexdigest()[:10]
    return f"tk-{ozet}"


def _birlestir(eski: Taslak, yeni: Taslak) -> Taslak:
    kaynak = min(eski.kaynak, yeni.kaynak, key=lambda k: _ONCELIK[k])
    kanit = tuple(dict.fromkeys((*eski.kanit, *yeni.kanit)))
    olcut, notu = (eski.olcut, eski.olcut_notu) if eski.olcut else (yeni.olcut, yeni.olcut_notu)
    return Taslak(
        id=eski.id,
        kaynak=kaynak,
        request=eski.request,
        olcut=olcut,
        olcut_notu=notu,
        kanit=kanit,
        olusturma=eski.olusturma,
    )


def _kisa(metin: str) -> str:
    return metin if len(metin) <= KANIT_UZUNLUGU else metin[:KANIT_UZUNLUGU] + "…"
