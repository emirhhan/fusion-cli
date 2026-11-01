"""`--exclude-dynamic-system-prompt-sections`: kişiye/makineye özgü bölümler ilk kullanıcı mesajına.

Claude Code'da bu bayrak kullanıcıya özgü bağlamı (otomatik bellek konumu gibi) sistem
isteminden ilk kullanıcı mesajına taşır; aynı görevi farklı kullanıcı ve makinelerde koşan
betiklerde istem önbelleği paylaşılır. Yalnız varsayılan sistem isteminde geçerlidir;
`--system-prompt(-file)` verilince yok sayılır (o durumda proje bağlamı zaten kullanıcı
mesajındadır).

Fusion'da dinamik bölümler: proje talimatları (CLAUDE.md/AGENTS.md katmanları), düz metin
bellek bloğu ve depo haritası. Bayrak koşu boyunca bir bağlam değişkeninde durur; yalnız kök
tur (derinlik 0) uygular, alt ajanlar kendi istemlerini değiştirmeden kurar.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_EXCLUDE: ContextVar[bool] = ContextVar("fusion_exclude_dynamic_sections", default=False)


def active() -> bool:
    """Bu koşuda dinamik bölümler sistem isteminden çıkarılıyor mu."""
    return _EXCLUDE.get()


@contextmanager
def excluded(enabled: bool) -> Iterator[None]:
    """Bu blok boyunca kök turun dinamik bölümleri ilk kullanıcı mesajına taşınsın."""
    token = _EXCLUDE.set(bool(enabled))
    try:
        yield
    finally:
        _EXCLUDE.reset(token)


def applies(*, depth: int, system_prompt: str | None) -> bool:
    """Bu turda taşıma yapılır mı: kök tur, varsayılan sistem istemi, bayrak açık."""
    return depth == 0 and system_prompt is None and active()


def user_context(*parts: str) -> str:
    """Taşınan bölümleri ilk kullanıcı mesajının bağlam metni olarak birleştir."""
    return "\n\n".join(part for part in parts if part)
