"""Web araç ölçümünü gerçek oturum ve adaptör kimliğine bağlar."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .models import WebSessionConfig


def web_adapter_revision() -> str:
    """Kurulu protokol ve web adaptörü; model sürümü tahmin edilmez."""
    root = Path(__file__).parents[1]
    sources = (
        "core/tool_emulation.py",
        "providers/web_browser.py",
        "providers/web_session.py",
        "providers/web_transport.py",
    )
    try:
        digest = hashlib.sha256()
        for name in sources:
            digest.update(name.encode())
            digest.update(b"\0")
            digest.update((root / name).read_bytes())
        return digest.hexdigest()
    except OSError:
        return ""  # Paketli runtime kaynak sürümünü bildiremiyorsa bilinmiyor kalır.


def web_evaluation_scope(session: WebSessionConfig) -> str:
    """Kimlik/scope paylaşılırken hesap adı ve uç ayrıntıları açıklanmaz."""
    identity = (
        session.provider,
        session.account,
        session.model,
        session.transport,
        session.selected_model,
        session.endpoint,
        session.credential_ref,
        session.tool_support,
    )
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


def web_evaluation_matches(session: WebSessionConfig) -> bool:
    """Legacy tarih/sürüm bilinmiyor kalır; bilinen eski kimlik geçerli sayılmaz."""
    if not session.tool_evaluation_scope:
        return True  # Eski izin politikası korunur; sunum legacy/unverified'dır.
    return (
        bool(session.tool_evaluation_adapter_revision)
        and session.tool_evaluation_scope == web_evaluation_scope(session)
        and session.tool_evaluation_adapter_revision == web_adapter_revision()
    )
