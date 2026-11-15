"""Her alt ajanın sistem istemine eklenen oturum metni (`--append-subagent-system-prompt`).

Claude Code'da `-p --append-subagent-system-prompt "<metin>"` iç içe olanlar dahil her alt
ajanın sistem isteminin sonuna eklenir; konuşmanın kendi istemini kullanan çatallı alt ajan
(fork) hariçtir. Metin koşu boyunca bir bağlam değişkeninde durur: `asyncio.run` bağlamı
kopyaladığı için koşunun bütün görevleri onu görür, başka koşulara sızmaz.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_APPEND: ContextVar[str] = ContextVar("fusion_subagent_append", default="")


def current() -> str:
    """Alt ajanlara eklenecek metin (yoksa boş)."""
    return _APPEND.get()


@contextmanager
def appended(text: str) -> Iterator[None]:
    """Bu blok boyunca başlatılan alt ajanların istemine `text` eklensin."""
    token = _APPEND.set(text.strip())
    try:
        yield
    finally:
        _APPEND.reset(token)
