"""Araç sonuçlarını gerçek çağrı kimliğiyle güncel yer belirleme kartına bağlar."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from ...core.constants import MAX_SEARCHABLE_FILE_BYTES
from ...core.localization import (
    MAX_LOCALIZATION_CANDIDATES,
    MAX_LOCALIZATION_LABEL_CHARS,
    MAX_LOCALIZATION_PATH_CHARS,
    MAX_LOCALIZATION_PROMPT_CHARS,
    LocalizationCandidate,
    LocalizationCard,
)
from ...core.redaction import redact
from ...core.source_read import read_scoped_source
from ...core.tools import ToolContext, ToolResult
from ...core.types import Message, ToolCall
from ...tools.search import is_searchable_source

_CARD_PREFIX = "KANITLI YER BELİRLEME KARTI"
_LIMIT_NOTE = "… Kartın sunum sınırına ulaşıldı; daha dar kaynak sorgusu kullan."
_EVIDENCE_TOOLS = frozenset({"search_code", "symbol_query"})


def _is_current(candidate: LocalizationCandidate, context: ToolContext) -> bool:
    path = Path(candidate.path)
    if path.is_absolute() or len(candidate.path) > MAX_LOCALIZATION_PATH_CHARS:
        return False
    root = context.root.resolve()
    if not is_searchable_source(root / path, root):
        return False
    source = read_scoped_source(root, path, max_bytes=MAX_SEARCHABLE_FILE_BYTES)
    return source is not None and hashlib.sha256(source).hexdigest() == candidate.source_digest


def _collect(call: ToolCall, result: ToolResult, context: ToolContext) -> LocalizationCard:
    entries = (result.structured or {}).get("localization_candidates", ()) if result.ok else ()
    candidates: list[LocalizationCandidate] = []
    if not isinstance(entries, (tuple, list)):
        entries = ()
    for entry in entries[:MAX_LOCALIZATION_CANDIDATES]:
        if not isinstance(entry, Mapping):
            continue
        path, symbol, digest = (entry.get(key) for key in ("path", "symbol", "source_digest"))
        if not all(isinstance(value, str) for value in (path, symbol, digest)):
            continue
        candidate = LocalizationCandidate(
            str(path), str(symbol)[:MAX_LOCALIZATION_LABEL_CHARS], call.id, str(digest)
        )
        if _is_current(candidate, context):
            candidates.append(candidate)
    return LocalizationCard(
        tuple(candidates),
        "Adayın göreve uygunluğu henüz doğrulanmadı; aynı adlı kaynakları karşılaştır.",
        "Yanlış adayda kalma; ilgili başka klasörde veya daha ayırt edici bir ifadeyle ara.",
    )


async def record_result(call: ToolCall, result: ToolResult, context: ToolContext) -> None:
    """Modelin kimlik iddiasını kullanmadan executor sonucunu bağla."""
    if context.localization.enabled and call.name in _EVIDENCE_TOOLS:
        context.localization.card = await asyncio.to_thread(_collect, call, result, context)


def card_text(context: ToolContext) -> str:
    """İçerik sızdırmadan yalnız güncel kaynak kanıtını sınırlı boyutta sun."""
    if not context.localization.enabled:
        return ""
    card = context.localization.card
    candidates = tuple(
        candidate for candidate in card.candidates if _is_current(candidate, context)
    )
    context.localization.card = replace(card, candidates=candidates)
    lines = [_CARD_PREFIX]
    if context.localization_step_id:
        lines.append(_binding_text(context))
    notes = [
        f"Belirsizlik: {redact(card.uncertainty)}",
        f"Sonraki arama: {redact(card.next_search)}",
    ]
    for candidate in candidates:
        line = "- " + json.dumps(
            {
                "path": redact(candidate.path),
                "symbol": redact(candidate.symbol),
                "evidence_call_id": redact(candidate.evidence_call_id)[
                    :MAX_LOCALIZATION_LABEL_CHARS
                ],
                "source_digest": redact(candidate.source_digest),
            },
            ensure_ascii=False,
        )
        if (
            len("\n".join([*lines, line, *notes])) + len(_LIMIT_NOTE) + 3
            > MAX_LOCALIZATION_PROMPT_CHARS
        ):
            lines.append(_LIMIT_NOTE)
            break
        lines.append(line)
    if not candidates:
        lines.append("Güncel kaynak kanıtı yok; modelin bildirdiği dosya adı kanıt sayılmaz.")
    return "\n".join([*lines, *notes]) + "\n\n"


def _binding_text(context: ToolContext) -> str:
    """Büyük plan kimlikleri de kartın sunum bütçesini aşamasın."""
    return "Adım/koşul bağı: " + json.dumps(
        {
            "step_id": redact(context.localization_step_id)[:MAX_LOCALIZATION_LABEL_CHARS],
            "criterion_ids": tuple(
                redact(criterion)[:MAX_LOCALIZATION_LABEL_CHARS]
                for criterion in context.localization_criterion_ids[:MAX_LOCALIZATION_CANDIDATES]
            ),
        },
        ensure_ascii=False,
    )


async def refresh_prompt(messages: list[Message], context: ToolContext) -> None:
    """Her sağlayıcı çağrısında eski kartı güncel kaynakla değiştir."""
    messages[:] = [
        message
        for message in messages
        if not (message.role == "system" and message.content.startswith(_CARD_PREFIX))
    ]
    if not context.localization.enabled:
        return
    text = await asyncio.to_thread(card_text, context)
    messages.append(Message("system", text))
