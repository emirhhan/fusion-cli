"""10.000 karakteri aşan kanca metni: dosyaya yazılır, modele yol + 2.000 karakter önizleme.

Claude Code `additionalContext`, `systemMessage` ve düz stdout için aynı kuralı uygular:
metin oturum dizinindeki bir dosyaya kaydedilir, yerine dosya yolu ve ilk 2.000 karakter
gelir. Dizin verilmezse (alt sistem testleri) metin kırpılır.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

from ...core.hooks.decision import HOOK_CONTEXT_CHARS
from ...core.hooks.events import HookVerdict

#: Aşımda modele verilen önizleme uzunluğu.
PREVIEW_CHARS = 2_000


def spill(text: str, directory: Path | None) -> str:
    """Sınırı aşan metni dosyaya yaz; yol + önizleme döndür."""
    if len(text) <= HOOK_CONTEXT_CHARS:
        return text
    if directory is None:
        return text[:HOOK_CONTEXT_CHARS]
    name = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    target = directory / f"hook-output-{name}.txt"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    except OSError:
        return text[:HOOK_CONTEXT_CHARS]
    return (
        f"Kanca çıktısı 10.000 karakteri aştı; tamamı: {target}\n"
        f"Önizleme (ilk 2.000 karakter):\n{text[:PREVIEW_CHARS]}"
    )


def spill_verdict(verdict: HookVerdict, directory: Path | None) -> HookVerdict:
    """Kararın bağlam ve kullanıcı metinlerini sınıra uydur."""
    context = tuple(spill(item, directory) for item in verdict.additional_context)
    system = tuple(spill(item, directory) for item in verdict.system_messages)
    if context == verdict.additional_context and system == verdict.system_messages:
        return verdict
    return replace(verdict, additional_context=context, system_messages=system)
