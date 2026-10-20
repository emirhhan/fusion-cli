"""Aynı dosyada ardışık küçük düzenleme serisini fark edip toplu yolu önermek.

Ölçüldü (17. kabul koşusu): model ürün veri dosyasını 27 ardışık `edit_file`
çağrısıyla tek tek düzeltti; her çağrı ~160 bin token'lık istemle gitti ve seri
~12 dakika sürdü. Aynı sırada önizlemenin bildirdiği büyük farklar bekledi.
Uyarı ARAÇ SONUCUNA eklenir: model sistem istemindeki kuralı atlıyor ama araç
sonucuna tepki veriyor (LangChain'in Nemotron 3 Ultra ölçümü de bu yönde).
"""

from __future__ import annotations

#: Bu kadar ardışık düzenlemeden sonra bir kez uyarılır.
EDIT_STREAK_THRESHOLD = 4

STREAK_NOTE = (
    "FUSION_NOT: '{path}' dosyasını art arda {count} kez küçük düzenlemeyle değiştirdin. "
    "Kalan değişiklikleri tek multi_edit çağrısında ya da run_shell ile küçük bir betikle "
    "(python/jq/sed) TOPLU yap; sonra işin asıl açık maddelerine dön."
)


def next_streak(previous: tuple[str, int], path: str) -> tuple[str, int]:
    """Aynı yola ardışık düzenleme sayacını ilerlet; yol değişince sıfırdan başla."""
    onceki_yol, sayi = previous
    return (path, sayi + 1) if path == onceki_yol else (path, 1)


def streak_note(streak: tuple[str, int]) -> str | None:
    """Eşiğe TAM ulaşıldığında bir kez not; sonraki düzenlemelerde tekrar etmez."""
    yol, sayi = streak
    if sayi != EDIT_STREAK_THRESHOLD:
        return None
    return STREAK_NOTE.format(path=yol, count=sayi)
