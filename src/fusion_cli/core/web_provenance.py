"""Adapter gözlemi ve uygulama korelasyonu; köken çalıştırma izni değildir."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .redaction import contains_sensitive

IDENTIFIER_LIMIT = 160
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*")
ASSISTANT_ROLE_EVIDENCE = frozenset(
    {
        "data-message-author-role=assistant",
        "data-markdown-text-style=assistant-message",
    }
)
PROTOCOL_VERSIONS = frozenset({"v1", "v2"})
ORIGIN_WARNING = "Yanıtın güncel assistant kökeni doğrulanamadı; değiştirici çağrıları ertele."
QUOTED_WARNING = "Alıntı veya kaynağı belirsiz çit içindeki çağrı yürütmeye alınmadı."


def safe_observed_identifier(value: object) -> str | None:
    """DOM kimliğinin yalnız dar, sır içermeyen gösterimini kabul et."""
    if not isinstance(value, str) or not 0 < len(value) <= IDENTIFIER_LIMIT:
        return None
    if _IDENTIFIER.fullmatch(value) is None or contains_sensitive(value):
        return None
    return value


@dataclass(frozen=True, slots=True)
class WebCallContext:
    """Mevcut tur/deneme otoritesinden ve çağrı yayıncısından gelen kimlikler."""

    session_id: str
    turn_id: str
    attempt_id: str
    model_call_id: str
    frame_id: str | None = None


@dataclass(frozen=True, slots=True)
class WebResponseProvenance:
    """Metinle aynı accepted snapshot'ta ölçülen veriler; bilinmeyen uydurulmaz."""

    transport_kind: str = "unknown"
    extraction_kind: str = "unknown"
    provider_id: str = "unknown"
    observed_message_id: str | None = None
    observed_container_id: str | None = None
    assistant_role_evidence: str | None = None
    selector_id: str | None = None
    selector_schema_version: str | None = None
    selector_bundle_digest: str | None = None
    adapter_revision: str | None = None
    observed_frontend_version: str | None = None
    observed_model: str | None = None
    freshness_basis: str = "unknown"
    origin_status: str = "unknown"
    content_kind: str = "unknown"
    call_context: WebCallContext | None = None

    def has_current_assistant_origin(self, expected: WebCallContext | None) -> bool:
        """Aynı çağrıya bağlanan ölçülmüş assistant gözlemini sınar; izin vermez."""
        return bool(
            expected is not None
            and self.call_context == expected
            and all(
                safe_observed_identifier(value)
                for value in (
                    expected.session_id,
                    expected.turn_id,
                    expected.attempt_id,
                    expected.model_call_id,
                )
            )
            and self.transport_kind == "browser"
            and self.extraction_kind == "dom_normalized_text"
            and self.origin_status == "observed_assistant"
            and self.assistant_role_evidence in ASSISTANT_ROLE_EVIDENCE
            and self.freshness_basis in {"new_node", "changed_node"}
            and safe_observed_identifier(self.observed_container_id) is not None
        )


def load_web_provenance(value: object) -> WebResponseProvenance | None:
    """Yerel replay alanlarını doğrula; beyanı gerçek yakalama kabulüne yükseltmez."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("Web kökeni nesne olmalı.")
    context_value = value.get("call_context")
    context = None
    if context_value is not None:
        if not isinstance(context_value, dict):
            raise ValueError("Web çağrı bağlamı nesne olmalı.")
        required = ("session_id", "turn_id", "attempt_id", "model_call_id")
        if any(safe_observed_identifier(context_value.get(key)) is None for key in required):
            raise ValueError("Web çağrı bağlamı kimlikleri geçersiz.")
        context = WebCallContext(
            session_id=str(context_value["session_id"]),
            turn_id=str(context_value["turn_id"]),
            attempt_id=str(context_value["attempt_id"]),
            model_call_id=str(context_value["model_call_id"]),
            frame_id=safe_observed_identifier(context_value.get("frame_id")),
        )
    fields = WebResponseProvenance.__dataclass_fields__
    if set(value) - set(fields):
        raise ValueError("Bilinmeyen web köken alanı.")
    values = {key: item for key, item in value.items() if key != "call_context"}
    if any(item is not None and not isinstance(item, str) for item in values.values()):
        raise ValueError("Web köken alanları metin olmalı.")
    return WebResponseProvenance(**values, call_context=context)
