"""Masaüstü için düz metin otomatik bellek RPC'leri: `otobellek.*` (P-036).

Ayarlar › Kişiselleştirme › "Otomatik bellek" paneli bu dört çağrıyla çalışır: durum +
indeks metni, indeksi kaydet (kullanıcı Markdown'ı yerinde düzenler), aç/kapa (kalıcı
`runtime.auto_memory`) ve Claude belleğinden içe aktar. REPL `/memory` ile aynı mantık;
iş `memory/plain_memory.py` ve `ReplState`'tedir.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from ..cli.repl.state import ReplState
from ..config.writer import write_runtime_flag
from ..history.claude_source import slug_for
from ..memory.plain_memory import (
    PROMPT_MAX_BYTES,
    PROMPT_MAX_LINES,
    PlainMemoryError,
    build_plain_memory,
    project_memory_dir,
)

#: Panelden kaydedilebilecek indeks boyutu; daha uzunu konu dosyalarına gitmeli.
INDEX_MAX_CHARS = 100_000


def status(state: ReplState) -> dict[str, Any]:
    """Durum + indeks metni; bellek kapalıysa yalnız `etkin: false` ve dizin."""
    from ..memory import auto_memory_location as location

    enabled = location.enabled(
        state.root, bool(getattr(state.config.runtime, "auto_memory", True))
    )
    directory = project_memory_dir(state.config, state.root)
    payload: dict[str, Any] = {
        "ok": True,
        "etkin": enabled,
        "dizin": str(directory),
        "dosya": str(directory / location.INDEX_FILE),
        "sinir_satir": PROMPT_MAX_LINES,
        "sinir_bayt": PROMPT_MAX_BYTES,
    }
    memory = state.plain_memory
    if not enabled or memory is None:
        return {**payload, "metin": "", "satir": 0, "bayt": 0, "kirpildi": False, "konular": []}
    current = memory.status()
    return {
        **payload,
        "metin": memory.read(),
        "satir": current.index_lines,
        "bayt": current.index_bytes,
        "kirpildi": current.truncated,
        "konular": list(current.topics),
    }


def save_index(state: ReplState, data: dict[str, Any]) -> dict[str, Any]:
    """Panelde düzenlenen `BELLEK.md` metnini olduğu gibi yaz (model değil, kullanıcı yazdı)."""
    memory = state.plain_memory
    if memory is None:
        return {"ok": False, "metin": "Otomatik bellek kapalı; önce aç."}
    text = data.get("metin")
    if not isinstance(text, str):
        return {"ok": False, "metin": "Bellek metni gerekli."}
    if len(text) > INDEX_MAX_CHARS:
        return {"ok": False, "metin": f"Bellek metni {INDEX_MAX_CHARS} karakteri aşamaz."}
    try:
        memory.write_index(text)
    except PlainMemoryError as error:
        return {"ok": False, "metin": str(error)}
    return status(state)


def set_enabled(state: ReplState, data: dict[str, Any]) -> dict[str, Any]:
    value = data.get("etkin")
    if not isinstance(value, bool):
        return {"ok": False, "metin": "Geçerli bir açık/kapalı değeri gerekli."}
    state.config = replace(state.config, runtime=replace(state.config.runtime, auto_memory=value))
    try:
        write_runtime_flag(state.config, "auto_memory", value)
    except (OSError, ValueError) as error:
        return {"ok": False, "metin": f"Ayar kaydedilemedi: {error}"}
    state.plain_memory = build_plain_memory(state.config, state.root)
    return status(state)


def import_external(state: ReplState, data: dict[str, Any]) -> dict[str, Any]:
    """`claude` belleğini (`~/.claude/projects/<proje>/memory`) içe aktar."""
    memory = state.plain_memory
    if memory is None:
        return {"ok": False, "metin": "Otomatik bellek kapalı; önce aç."}
    source = str(data.get("kaynak") or "claude").lower()
    if source != "claude":
        return {"ok": False, "metin": "Yalnız 'claude' kaynağı destekleniyor."}
    source_dir = state.home / ".claude" / "projects" / slug_for(state.root) / "memory"
    count = memory.import_markdown(source_dir, source=source)
    if count == 0:
        return {"ok": False, "metin": f"Claude belleği bulunamadı: {source_dir}"}
    return {**status(state), "alinan": count}
