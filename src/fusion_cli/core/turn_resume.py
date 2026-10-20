"""Kesilen turun kanıtlarını koruyan, araç çalıştırmayan devam bağlamı."""

from __future__ import annotations

from collections.abc import Sequence

from .types import Message

RESUME_PREFIX = "[Kesilen turun devam bağlamı]"
UNKNOWN_TOOL_RESULT = (
    "Tur bu araç çağrısı sırasında kesildi; sonuç kaydedilmedi. İşlem gerçekleşmiş "
    "olabilir. Aynı işlemi yeniden çalıştırmadan önce dosyadan veya ilgili sistemden "
    "sonucu salt okunur biçimde doğrula; başarı veya başarısızlık varsayma."
)


def interrupted_history(messages: Sequence[Message], *, task: str, root: str) -> list[Message]:
    """Eksik araç sonuçlarını belirsiz olarak kapat, tek devam notu ekle.

    Eksik sonuç başarı sayılmaz ve otomatik tekrarlanmaz. Kaydedilmiş araç
    sonuçları aynen korunur; henüz başlamamış çağrılar da belirsiz kabul edilir.
    """
    history: list[Message] = []
    pending: dict[str, str] = {}

    def close_pending() -> None:
        for identifier, name in pending.items():
            history.append(
                Message("tool", UNKNOWN_TOOL_RESULT, tool_call_id=identifier, name=name, ok=False)
            )
        pending.clear()

    for message in messages:
        if message.harness_note and message.content.startswith(RESUME_PREFIX):
            continue
        if message.role != "tool":
            close_pending()
        elif message.tool_call_id:
            pending.pop(message.tool_call_id, None)
        history.append(message)
        pending.update((call.id, call.name) for call in message.tool_calls)
    close_pending()
    history.append(
        Message(
            "user",
            f"{RESUME_PREFIX}\n"
            f"Asıl görev: {task}\nProje kökü (sondaki boşluklar dahil): {root!r}\n"
            "Önceki araç çağrıları ve sonuçları yukarıda kayıtlı. Tamamlanan işleri, "
            "araştırmayı ve dosyaları yeniden oluşturma. Son araç sonucunu esas alıp "
            "yarım kalan adımdan sürdür. Mevcut dosyada gerekirse yalnız ilgili "
            "bölümü oku ve değiştir. Sonucu belirsiz bir işlemi tekrarlamadan önce "
            "gerçek durumunu doğrula. Kullanıcı turu durdurdu: yeni mesaj gelmeden kendiliğinden "
            "araç çalıştırma. Kullanıcı devam et veya yeni talimat yazınca bu noktadan hemen "
            "sürdür; önce gerçek durumu doğrula (ör. kodu çalıştır) ve aynı yanıtı ya da aynı "
            "düzenlemeyi tekrarlama.",
            harness_note=True,
        )
    )
    return history
