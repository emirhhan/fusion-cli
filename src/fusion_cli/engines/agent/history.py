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
#:
#: Değer havuzun EN DAR bağlam penceresinden türetilir; en genişinden değil, çünkü
#: yedeğe düşen tur da aynı geçmişi taşır. En dar pencere gpt-oss-20b'de 131.072
#: token (karşılaştırma: nemotron-3-super 262.144–1.000.000).
#:
#:   kullanılabilir ≈ 131.072 − çıktı bütçesi (8.192) − sistem promptu + araç şemaları (~4.000)
#:                  ≈ 119.000 token
#:   geçmişe ayrılan ≈ yarısı ≈ 59.000 token
#:   Türkçe + kod için ihtiyatlı oran 3 karakter/token ≈ 177.000 karakter
#:
#: Eski değer 24.000 karakterdi (≈6k token): en dar pencerenin bile %5'i. Agent üç beş
#: dosya okur okumaz geçmişini bir özete indiriyor, az önce okuduğunu unutuyordu.
COMPRESS_THRESHOLD_CHARS = 177_000
#: Sıkıştırmada birebir korunacak en son mesaj sayısı.
#:
#: Bir araç turu İKİ mesajdır (çağrı + sonuç), yani 6 yalnızca 3 tur demekti: özet
#: alındığı anda agent son üç adımı dışında her şeyi kaybediyordu. 20 mesaj ≈ 10 araç
#: turu — sıkıştırmadan sonra işe devam edebilecek kadar somut bağlam kalır.
KEEP_RECENT_MESSAGES = 20
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


#: İz sınıra sığmadığında başa konan işaret. Denetçi eksik bilgiyle çalıştığını bilmeli.
ELISION_NOTE = "[… önceki adımlar atlandı …]"


def transcript(
    messages: Sequence[Message],
    limit: int = TRACE_TOTAL_CHARS,
    *,
    message_chars: int = TRACE_MESSAGE_CHARS,
) -> str:
    """Denetim ve özet için kısa oturum izi çıkar.

    Araç çağrıları ve sonuçları (özellikle hatalar) korunur: denetçi modelin işin
    gerçekten yapılıp yapılmadığını anlaması buna bağlıdır.

    Sınır aşılırsa BAŞTAN değil SONDAN tutulur. Eskiden `[:limit]` ile ilk satırlar
    saklanıyordu; 60 adımlık bir turda denetçiye yalnızca ilk 10 adım gidiyor, üretilen
    hiçbir dosyayı görmeden "TAMAM" diyordu. Bir turun sonucu sonunda olur.
    """
    lines: list[str] = []
    for message in messages:
        lines.extend(_describe(message, message_chars))

    tam = "\n".join(lines)
    if len(tam) <= limit:
        return tam

    # Satır bütünlüğünü koru: sondan başlayarak sığdığı kadar satır al.
    butce = limit - len(ELISION_NOTE) - 1
    tutulan: list[str] = []
    for line in reversed(lines):
        if len(line) + 1 > butce:
            break
        tutulan.append(line)
        butce -= len(line) + 1
    tutulan.reverse()
    return "\n".join([ELISION_NOTE, *tutulan])


def _describe(message: Message, message_chars: int = TRACE_MESSAGE_CHARS) -> list[str]:
    excerpt = message.content[:message_chars]
    if message.role == "user" and message.content:
        return [f"[kullanıcı] {excerpt}"]
    if message.role == "tool":
        # Başarı bilgisi mesajın kendisinde taşınır; metinden tahmin edilmez.
        flag = " ⟵ HATA" if message.ok is False else ""
        return [f"[sonuç {message.name or ''}{flag}] {excerpt}"]
    if message.role == "assistant":
        # Argüman kesme payı mesaj payıyla birlikte büyür: sabit 200 karakter,
        # denetçiye `write_file`'ın yalnızca yolunu gösterip ne yazdığını gizliyordu.
        described = [
            f"[araç çağrısı] {call.name}({call.arguments[:message_chars]})"
            for call in message.tool_calls
        ]
        if message.content:
            described.append(f"[asistan] {excerpt}")
        return described
    return []
