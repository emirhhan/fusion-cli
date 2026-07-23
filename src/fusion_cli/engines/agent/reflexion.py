"""Refleksiyon — araç hatasından sonra modele yön veren not.

EK MODEL ÇAĞRISI YAPMAZ: yalnızca geçmişe kısa bir kullanıcı mesajı enjekte eder.
Amaç, modelin aynı hatalı çağrıyı körlemesine tekrarlamasını önlemektir; bu bedava
bir davranış düzeltmesidir.

`goal` kipinde daha ısrarcı bir varyant kullanılır: orada pes etmek yasaktır.
"""

from __future__ import annotations

from ...core.types import Message

STANDARD_NOTE = (
    "[refleksiyon] Son araç çağrılarından en az biri HATA döndürdü. Kısaca ne yanlış "
    "gitti düşün ve FARKLI bir yaklaşım dene — aynı çağrıyı birebir tekrarlama. "
    "Gerekirse önce keşif yap (read_file / search_code), sonra hedefli düzelt."
)

PERSISTENT_NOTE = (
    "[refleksiyon] Son araç çağrısı HATA döndürdü. Pes etme: hatayı dikkatlice oku ve "
    "farklı bir yol, araç ya da parametre dene. Kendi başına aşamayacağın bir durumsa "
    "ask_user ile kullanıcıdan destek iste."
)

AUTO_CONTINUE_NOTE = (
    "[otomatik-devam] İşi yarım bıraktın gibi görünüyor. Niyet beyan etmek yerine ya bir "
    "araç çağırıp devam et ya da somut nihai teslimi ver. Zaten bittiyse tek cümleyle teyit et."
)


def note(*, persistent: bool) -> Message:
    """Araç hatasından sonra enjekte edilecek refleksiyon mesajı."""
    return Message("user", PERSISTENT_NOTE if persistent else STANDARD_NOTE)


def auto_continue_note() -> Message:
    return Message("user", AUTO_CONTINUE_NOTE)


def looks_unfinished(
    final_text: str, *, tool_calls_last_turn: int, has_pending_todos: bool
) -> bool:
    """Model araçsız bitirdi ama iş açıkça yarım mı?

    Dil-bağımsız iki sezgisel:
    - Tamamlanmamış todo maddesi varsa iş bitmemiştir.
    - Bu turda araç çağrıldıysa ama nihai metin çok kısa ve kod/teslim içermiyorsa,
      model işe başlayıp bitirmeden durmuş olabilir.
    """
    if has_pending_todos:
        return True
    text = final_text.strip()
    return tool_calls_last_turn > 0 and len(text) < 80 and "`" not in text
