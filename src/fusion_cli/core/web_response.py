"""Web yanıtının bütünlüğünü tek yerde sınıflandırır.

Tarayıcı taşımasında kayıp üç ayrı biçimde gelir ve üçü FARKLI kurtarma ister:

- **Boş yanıt:** model hiç üretmedi ya da arayüz bloğu sildi. Doğru hamle aynı
  isteği sadeleştirip tekrar sormaktır.
- **Kesilmiş yanıt:** üretim çıktı bütçesinde bitti. Doğru hamle "kaldığın yerden
  devam et" demektir; baştan sormak yapılan işi çöpe atar.
- **Kapanmamış blok:** sözleşme yarıda kaldı; metin var ama çağrı okunamaz. Doğru
  hamle sözleşmeyi hatırlatıp SADECE eksik bloğu istemektir.

Bunları tek bir "model boş cevap verdi" kutusuna koymak, koşuların neden bittiğini
görünmez kılıyordu (ölçüldü, 5-6 Eylül). Sınıflandırma saftır: metne ve sağlayıcının
bildirdiği kesilme bayrağına bakar.
"""

from __future__ import annotations

from enum import StrEnum

from .tool_emulation import (
    CALL_CLOSE,
    CALL_OPEN,
    LEGACY_CALL_CLOSE,
    LEGACY_CALL_OPEN,
    LEGACY_PAYLOAD_CLOSE,
    PAYLOAD_CLOSE,
    PAYLOAD_OPEN,
)

_ACIK_KAPALI = (
    (CALL_OPEN, CALL_CLOSE),
    (PAYLOAD_OPEN, PAYLOAD_CLOSE),
    (LEGACY_CALL_OPEN, LEGACY_CALL_CLOSE),
    ("<tool_payload", LEGACY_PAYLOAD_CLOSE),
)


class ResponseIntegrity(StrEnum):
    """Bir web yanıtının bütünlük durumu."""

    OK = "ok"
    EMPTY = "empty"
    TRUNCATED = "truncated"
    UNCLOSED_BLOCK = "unclosed_block"


def classify_response(text: str, *, truncated: bool, has_tool_calls: bool) -> ResponseIntegrity:
    """Yanıtı bütünlük sınıfına ayır.

    Sağlayıcının bildirdiği kesilme, metne bakan her sezgiden önce gelir: bu bir
    olgudur, tahmin değil. Araç çağrısı üreten tur metin üretmeyebilir; bu kayıp
    sayılmaz.
    """
    if truncated:
        return ResponseIntegrity.TRUNCATED
    if _acik_blok(text):
        return ResponseIntegrity.UNCLOSED_BLOCK
    if has_tool_calls:
        return ResponseIntegrity.OK
    if not text.strip():
        return ResponseIntegrity.EMPTY
    return ResponseIntegrity.OK


def _acik_blok(text: str) -> bool:
    """Açılıp kapanmamış bir sözleşme bloğu var mı?"""
    return any(
        text.count(acik) > text.count(kapali) for acik, kapali in _ACIK_KAPALI if acik in text
    )
