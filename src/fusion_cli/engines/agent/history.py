"""Konuşma geçmişi üzerinde saf işlemler.

Ağ ve model çağrısı yoktur; doğrudan test edilir. Buradaki iki kural, uzun oturumları
bozan iki klasik hatayı önler:

1. **Kesme noktası bir `user` turunun başında olmalıdır.** Bir `assistant` mesajı araç
   çağrısı taşıyorsa onu izleyen `tool` sonuçlarından ayrılamaz; ayrılırsa sağlayıcı
   "orphan tool call" hatası verir. Bu yüzden kesim daima güvenli sınıra kaydırılır.
2. **Sıkıştırma başarısızsa geçmişe dokunulmaz.** Yarım özet, hiç özetten kötüdür.
"""

from __future__ import annotations

from collections.abc import Sequence

from ...core.types import Message

#: Geçmiş bu karakter sayısını aşınca sıkıştırma denenir.
COMPRESS_THRESHOLD_CHARS = 24_000
#: Sıkıştırmada birebir korunacak en son mesaj sayısı.
KEEP_RECENT_MESSAGES = 6
#: Oturum izinde tek bir mesajdan alınacak en fazla karakter.
TRACE_MESSAGE_CHARS = 300
#: Oturum izinin toplam uzunluğu.
TRACE_TOTAL_CHARS = 3_000


def total_chars(messages: Sequence[Message]) -> int:
    """Geçmişin kabaca büyüklüğü."""
    return sum(len(message.content) for message in messages)


def needs_compression(messages: Sequence[Message]) -> bool:
    return total_chars(messages) >= COMPRESS_THRESHOLD_CHARS


def safe_cut(messages: Sequence[Message], keep_recent: int = KEEP_RECENT_MESSAGES) -> int:
    """Son `keep_recent` mesajı korurken güvenli kesme indeksini bul.

    Kesim noktası bir `user` mesajına kaydırılır; araç çağrısı ile sonucu ayrılmaz.
    Güvenli nokta yoksa 0 döner (sıkıştırma yapılmaz).
    """
    start = max(0, len(messages) - keep_recent)
    while start < len(messages) and messages[start].role != "user":
        start += 1
    return 0 if start >= len(messages) else start


def transcript(messages: Sequence[Message], limit: int = TRACE_TOTAL_CHARS) -> str:
    """Denetim ve özet için kısa oturum izi çıkar.

    Araç çağrıları ve sonuçları (özellikle hatalar) korunur: denetçi modelin işin
    gerçekten yapılıp yapılmadığını anlaması buna bağlıdır.
    """
    lines: list[str] = []
    for message in messages:
        lines.extend(_describe(message))
    return "\n".join(lines)[:limit]


def _describe(message: Message) -> list[str]:
    excerpt = message.content[:TRACE_MESSAGE_CHARS]
    if message.role == "user" and message.content:
        return [f"[kullanıcı] {excerpt}"]
    if message.role == "tool":
        # Başarı bilgisi mesajın kendisinde taşınır; metinden tahmin edilmez.
        flag = " ⟵ HATA" if message.ok is False else ""
        return [f"[sonuç {message.name or ''}{flag}] {excerpt}"]
    if message.role == "assistant":
        described = [
            f"[araç çağrısı] {call.name}({call.arguments[:200]})" for call in message.tool_calls
        ]
        if message.content:
            described.append(f"[asistan] {excerpt}")
        return described
    return []
