"""Görüntülenecek metin üzerinde saf dönüşümler.

Reasoning modelleri cevaptan önce "düşünme" metni üretir ve bunu `<think>…</think>`
bloklarına sarar. Bu metin kullanıcıya gösterilmemelidir: hem çok uzundur hem de
cevabın kendisi değildir.

Akışta ayıklama iki yerde zorlaşır ve ikisi de burada ele alınır:

1. **Kapanmamış açılış** — `<think>` görüldüğünde kapanışı henüz gelmemiştir.
   Sonrası geri tutulur; kapanış gelince zaten atılacaktır.
2. **Yarım açılış etiketi** — parça `"<th"` olarak gelebilir. Bu da geri tutulur,
   yoksa etiketin başı ekrana sızar. Tur bitince (`streaming=False`) geri tutulan
   parça serbest bırakılır: gerçekten `<` ile biten bir cevap kaybolmaz.
"""

from __future__ import annotations

import re

THINK_OPEN = "<think>"
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_thinking(text: str, *, streaming: bool = False) -> str:
    """Görünür metni düşünme bloklarından arındır.

    `streaming=True` iken, tamamlanmamış bir açılış etiketi olabilecek son parça da
    geri tutulur. Akış bittiğinde `streaming=False` ile çağır: geri tutulan varsa
    serbest bırakılır.
    """
    visible = _THINK_BLOCK.sub("", text)
    opening = visible.find(THINK_OPEN)
    if opening != -1:
        return visible[:opening]
    if streaming:
        pending = _pending_open_length(visible)
        if pending:
            return visible[:-pending]
    return visible


def _pending_open_length(text: str) -> int:
    """Metnin sonundaki, `<think>` etiketinin başlangıcı olabilecek parçanın uzunluğu."""
    for length in range(min(len(THINK_OPEN) - 1, len(text)), 0, -1):
        if text.endswith(THINK_OPEN[:length]):
            return length
    return 0
