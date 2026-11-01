"""`credentials.envVars` `mode: mask`: sandbox ortamına yer tutucu, proxy'ye gerçek değer (#368).

Claude Code: sandbox içindeki komut oturum başına bir yer tutucu (sentinel) görür; sandbox
proxy'si izinli ana makinelere (`injectHosts`, yoksa `allowedDomains`) giden istekte gerçek
değeri koyar. HTTPS için `network.tlsTerminate`, düz HTTP için `allowPlaintextInject` gerekir;
ikisi de yoksa komut yalnız yer tutucuyu görür (istek kimliksiz gider, sır sızmaz).

Yer tutucu gerçek değerle aynı uzunluktadır (bkz. `core.sandbox_tls`) ve oturum boyunca aynı
kalır.
"""

from __future__ import annotations

import secrets
import string
import threading
from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING

from ..core.errors import FusionError
from ..core.sandbox_policy import SandboxPolicy, domain_allowed
from ..core.sandbox_tls import Injection

if TYPE_CHECKING:
    from .sandbox_ca import SessionCa

__all__ = ["MaskSpec", "apply_masks", "parse_mask_entries", "prepare_tls"]

_ALPHABET = string.ascii_letters + string.digits
#: Uzun değerde yer tutucunun tanınır ön eki.
_PREFIX = "FUSIONMASK"
_LOCK = threading.Lock()
#: (ad, değer) → yer tutucu; oturum boyunca aynı.
_SENTINELS: dict[tuple[str, str], str] = {}

MaskSpec = tuple[str, tuple[str, ...]]


def parse_mask_entries(entries: tuple[str, ...]) -> tuple[MaskSpec, ...]:
    """`AD` ya da `AD=host1,host2` → (ad, injectHosts)."""
    result: list[MaskSpec] = []
    for entry in entries:
        name, _, hosts = entry.partition("=")
        if name.strip():
            result.append((name.strip(), tuple(h.strip() for h in hosts.split(",") if h.strip())))
    return tuple(result)


def _sentinel(name: str, value: str) -> str:
    with _LOCK:
        existing = _SENTINELS.get((name, value))
        if existing is not None:
            return existing
        size = len(value.encode("utf-8"))  # bayt uzunluğu eşit: akış sınırları bozulmaz
        prefix = _PREFIX if size >= len(_PREFIX) + 8 else ""
        body = "".join(secrets.choice(_ALPHABET) for _ in range(size - len(prefix)))
        sentinel = prefix + body
        if sentinel == value:  # olasılık dışı; yine de gerçek değer verilmez
            sentinel = sentinel[::-1]
        _SENTINELS[(name, value)] = sentinel
        return sentinel


def _covered(host: str, policy: SandboxPolicy) -> bool:
    return host in policy.allowed_domains or domain_allowed(host.removeprefix("*."), policy)


def apply_masks(
    env: Mapping[str, str], policy: SandboxPolicy
) -> tuple[dict[str, str], tuple[Injection, ...]]:
    """Maskeli adları yer tutucuyla değiştir; proxy'nin yerine koyacağı değerleri döndür."""
    result = dict(env)
    injections: list[Injection] = []
    for name, hosts in parse_mask_entries(policy.mask_env):
        value = env.get(name)
        if not value or name in policy.deny_env:
            continue
        sentinel = _sentinel(name, value)
        result[name] = sentinel
        # Claude: her injectHosts girdisi allowedDomains kapsamında olmalı.
        targets = (
            tuple(h for h in hosts if _covered(h, policy)) if hosts else policy.allowed_domains
        )
        injections.append(
            Injection(sentinel.encode("utf-8"), value.encode("utf-8"), tuple(targets))
        )
    return result, tuple(injections)


def prepare_tls(
    policy: SandboxPolicy, notices: list[str]
) -> tuple[SandboxPolicy, SessionCa | None]:
    """`tlsTerminate` açıksa oturum CA'sı; anahtar dizini sandbox'a okunamaz yapılır.

    CA kurulamazsa (kullanıcı CA'sı okunamadı) bir not düşülür ve HTTPS sonlandırılmaz; maskeli
    değerler yine yer tutucudur (yerine konmaz, sızmaz).
    """
    if not policy.tls_terminate or not policy.restricts_network or policy.external_proxy:
        return policy, None
    try:
        from .sandbox_ca import session_ca  # cryptography yalnız gerekince yüklenir

        ca = session_ca(policy.tls_ca_cert, policy.tls_ca_key)
    except (FusionError, OSError, ImportError) as error:
        notices.append(f"TLS sonlandırma kullanılamıyor ({error}); mask değerleri yerine konmaz.")
        return policy, None
    locked = (*policy.locked_read, ca.private_dir)
    return replace(policy, locked_read=locked, deny_read=(*policy.deny_read, ca.private_dir)), ca
