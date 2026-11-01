"""Chrome dosya yükleme güvenlik denetimleri (#437).

Claude Code (`chrome` › Upload files to web pages): toplam en çok 10 MB; Read'i yasaklayan
izin kuralı yüklemeyi de engeller; birden çok sabit bağlantısı (hard link) olan dosya
reddedilir; `.env`, `.pem`, `.key` ya da `.ssh` altındaki gibi kimlik bilgisi adı taşıyan
dosyalar reddedilir. Fusion'da okuma engeli `sandbox.deny_read` (Fusion sırları dahil)
listesinden okunur.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..core.tools import ToolContext

#: Kimlik bilgisi taşıyan dosya adları (küçük harf) ve uzantıları.
_CREDENTIAL_NAMES = frozenset(
    {".env", ".netrc", ".npmrc", ".pypirc", "credentials", "id_rsa", "id_dsa", "id_ecdsa",
     "id_ed25519", ".git-credentials", "secrets.json", "secrets.yaml", "secrets.yml"}
)  # fmt: skip
_CREDENTIAL_SUFFIXES = frozenset({".pem", ".key", ".p12", ".pfx", ".keystore", ".jks"})
#: Altındaki her dosyanın kimlik bilgisi sayıldığı klasörler.
_CREDENTIAL_DIRS = frozenset({".ssh", ".gnupg", ".aws", ".kube", ".docker"})

HARD_LINK_REASON = "{name}: birden çok sabit bağlantısı (hard link) var; yüklenmez"
CREDENTIAL_REASON = "{name}: kimlik bilgisi dosyası gibi görünüyor; yüklenmez"
DENY_READ_REASON = "{name}: okuması yasak bir yolda (sandbox.deny_read); yüklenmez"


def _is_credential(path: Path) -> bool:
    name = path.name.casefold()
    if name in _CREDENTIAL_NAMES or name.startswith(".env."):
        return True
    if path.suffix.casefold() in _CREDENTIAL_SUFFIXES:
        return True
    return any(part.casefold() in _CREDENTIAL_DIRS for part in path.parts[:-1])


def _read_denied(path: Path, context: ToolContext) -> bool:
    policy = getattr(context, "sandbox_policy", None)
    denied = getattr(policy, "deny_read", ()) if policy is not None else ()
    resolved = path.resolve()
    return any(resolved == item.resolve() or item.resolve() in resolved.parents for item in denied)


def upload_refusal(path: Path, context: ToolContext) -> str | None:
    """Dosya yüklenemezse gerekçesi; yüklenebilirse None."""
    if _is_credential(path) or _is_credential(path.resolve()):
        return CREDENTIAL_REASON.format(name=path.name)
    if _read_denied(path, context):
        return DENY_READ_REASON.format(name=path.name)
    try:
        links = os.stat(path).st_nlink
    except OSError:
        return None
    return HARD_LINK_REASON.format(name=path.name) if links > 1 else None
