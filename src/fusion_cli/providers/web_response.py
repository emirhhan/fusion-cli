"""Accepted DOM gözlemi: metin ve köken tek snapshot'tan birlikte taşınır."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TypedDict

from ..core.web_provenance import (
    ASSISTANT_ROLE_EVIDENCE,
    WebCallContext,
    WebResponseProvenance,
    safe_observed_identifier,
)

ADAPTER_REVISION = "fusion-dom-origin-v2"


@dataclass(frozen=True, slots=True)
class ObservedResponse:
    """Normalleştirilmiş adapter metni; wire bytes veya model token akışı değildir."""

    text: str
    provenance: WebResponseProvenance


def observed_response(
    text: str,
    value: object,
    *,
    provider_id: str,
    selector: str,
    selector_version: str,
    selector_digest: str,
) -> ObservedResponse:
    """Ham DOM attribute'larını dar allowlist ile temizle; metin fallback'i unknown'dur."""
    origin = value.get("origin") if isinstance(value, dict) else None
    origin = origin if isinstance(origin, dict) else {}
    role = origin.get("role")
    role = role if isinstance(role, str) and role in ASSISTANT_ROLE_EVIDENCE else None
    container_id = safe_observed_identifier(origin.get("container_id"))
    quoted = origin.get("quoted")
    return ObservedResponse(
        text,
        WebResponseProvenance(
            transport_kind="browser",
            extraction_kind="dom_normalized_text" if origin else "text_fallback",
            provider_id=provider_id,
            observed_container_id=container_id,
            observed_message_id=safe_observed_identifier(origin.get("message_id")),
            assistant_role_evidence=role,
            selector_id=selector,
            selector_schema_version=selector_version,
            selector_bundle_digest=selector_digest,
            adapter_revision=ADAPTER_REVISION,
            origin_status="observed_assistant" if role and container_id else "unknown",
            content_kind="quoted" if quoted is True else "direct" if quoted is False else "unknown",
        ),
    )


def accept_observation(
    observation: ObservedResponse, *, freshness: str, context: WebCallContext | None
) -> ObservedResponse:
    """Yalnız bekleyicinin kabul ettiği gözleme bu çağrının korelasyonunu bağla."""
    return replace(
        observation,
        provenance=replace(observation.provenance, freshness_basis=freshness, call_context=context),
    )


def origin_script(roles: tuple[str, ...], identifiers: tuple[str, ...]) -> str:
    """Paket seçicileriyle DOM okumasına aynı evaluate_all içinde köken ekle."""
    return """(() => {
      const roles = ROLES, identifiers = IDENTIFIERS;
      for (const evidence of roles) {
        const [attribute, expected] = evidence.split('=');
        const container = node.closest('[' + attribute + ']');
        if (!container || container.getAttribute(attribute) !== expected) continue;
        let identity = identifiers.map(name => container.getAttribute(name)).find(Boolean);
        if (!identity && identifiers.includes('data-content-search-unit-key')) {
          const owner = container.closest('[data-content-search-unit-key]');
          const key = owner?.getAttribute('data-content-search-unit-key');
          if (key?.endsWith(':assistant')) identity = key;
        }
        return {role: evidence, container_id: identity ?? null,
          message_id: null, quoted: !!(node.closest('blockquote,q') ||
            node.querySelector('blockquote,q'))};
      }
      return {};
    })()""".replace("ROLES", json.dumps(roles)).replace("IDENTIFIERS", json.dumps(identifiers))


class ObservationOptions(TypedDict, total=False):
    """Bağlam olmayan legacy taşıma çağrısına yeni parametre ekleme."""

    observation_sink: Callable[[ObservedResponse], None]
    web_call_context: WebCallContext


def observation_options(
    context: WebCallContext | None, sink: Callable[[ObservedResponse], None] | None
) -> ObservationOptions:
    """Köken ölçümü yalnız uygulama çağrısına bağlanabiliyorsa etkinleşir."""
    if context is None or sink is None:
        return {}
    return {"web_call_context": context, "observation_sink": sink}


def accepted_snapshot(
    observation: ObservedResponse,
    before: tuple[ObservedResponse, ...],
    *,
    has_new_node: bool,
    context: WebCallContext | None,
) -> ObservedResponse:
    """Sanallaştırma/yeniden kullanılan kimlik için tazelik uydurma."""
    identity = observation.provenance.observed_container_id
    previous = {item.provenance.observed_container_id for item in before}
    freshness = "new_node" if has_new_node and identity and identity not in previous else "unknown"
    return accept_observation(observation, freshness=freshness, context=context)
