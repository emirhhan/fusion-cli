"""`--betas`: Anthropic API isteklerine eklenen `anthropic-beta` başlıkları (#301).

Claude Code'da `claude --betas interleaved-thinking` verilen beta adlarını API isteğine
başlık olarak ekler ve yalnız API anahtarı kullanıcılarına uygulanır. Fusion'da yalnız
Anthropic API'sine (LiteLLM `anthropic/…` modelleri) giden çağrılara eklenir; başka
sağlayıcının uç noktası bu başlığı tanımadığı için gönderilmez. Değer koşu boyunca bir bağlam
değişkeninde durur: `asyncio.run` bağlamı kopyaladığı için koşunun görevleri onu görür.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

HEADER = "anthropic-beta"
_BETAS: ContextVar[tuple[str, ...]] = ContextVar("fusion_anthropic_betas", default=())


def parse(values: Iterable[str]) -> tuple[str, ...]:
    """Bayrak değerlerini (virgülle ya da tekrarla) sıralı, tekrarsız beta adlarına çevir."""
    seen: list[str] = []
    for value in values:
        for name in value.replace(",", " ").split():
            if name not in seen:
                seen.append(name)
    return tuple(seen)


def current() -> tuple[str, ...]:
    """Bu koşunun beta adları (yoksa boş)."""
    return _BETAS.get()


@contextmanager
def enabled(betas: tuple[str, ...]) -> Iterator[None]:
    """Bu blok boyunca Anthropic çağrılarına `betas` başlığı eklensin."""
    token = _BETAS.set(tuple(betas))
    try:
        yield
    finally:
        _BETAS.reset(token)


def is_anthropic_model(model: str) -> bool:
    """LiteLLM model kimliği Anthropic API'sine mi gidiyor."""
    return model.startswith("anthropic/")


def headers_for(model: str) -> dict[str, str]:
    """Bu modelin isteğine eklenecek başlıklar (beta yoksa ya da Anthropic değilse boş)."""
    betas = current()
    if not betas or not is_anthropic_model(model):
        return {}
    return {HEADER: ",".join(betas)}
