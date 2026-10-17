"""Uzak izin kapsamları. Uzaktan erişim yerelden yüksek yetkili olamaz."""

from __future__ import annotations

from enum import StrEnum


class Scope(StrEnum):
    """Sabit kapsamlar; `kits.run.<id>` ve `mcp.*.<sağlayıcı>` ayrıca ön ekle işlenir."""

    PROJECT_READ = "project.read"
    PROJECT_WRITE = "project.write"
    AGENT_RUN = "agent.run"
    AGENT_PAUSE = "agent.pause"
    AGENT_CANCEL = "agent.cancel"
    KITS_LIST = "kits.list"
    DESKTOP_OBSERVE = "desktop.observe"
    DESKTOP_CONTROL = "desktop.control"
    PRODUCTION_DEPLOY = "production.deploy"


#: Varsayılan eşleştirme: salt okunur + izinli ajan görevi.
DEFAULT_SCOPES: frozenset[str] = frozenset(
    {Scope.PROJECT_READ.value, Scope.AGENT_RUN.value, Scope.AGENT_CANCEL.value}
)

#: Açık kullanıcı seçimi ve adım adım (step-up) onay gerektiren kapsamlar.
ELEVATED_SCOPES: frozenset[str] = frozenset(
    {
        Scope.PROJECT_WRITE.value,
        Scope.DESKTOP_OBSERVE.value,
        Scope.DESKTOP_CONTROL.value,
        Scope.PRODUCTION_DEPLOY.value,
    }
)

_PREFIXED = ("kits.run.", "mcp.read.", "mcp.write.")
_ELEVATED_PREFIXES = ("mcp.write.",)


def is_valid_scope(scope: str) -> bool:
    """Bilinen sabit ya da ön ekli kapsam mı?"""
    if scope in {item.value for item in Scope}:
        return True
    return any(scope.startswith(prefix) and len(scope) > len(prefix) for prefix in _PREFIXED)


def is_elevated(scope: str) -> bool:
    """Eşleştirmede açık seçim ve onayda step-up isteyen kapsam mı?"""
    return scope in ELEVATED_SCOPES or any(scope.startswith(p) for p in _ELEVATED_PREFIXES)


def parse_scopes(raw: object) -> frozenset[str]:
    """Kullanıcı girdisini doğrula; bilinmeyen kapsam sessizce yutulmaz."""
    if raw is None:
        return DEFAULT_SCOPES
    if not isinstance(raw, (list, tuple, set, frozenset)):
        raise ValueError("Kapsamlar liste olmalıdır.")
    scopes: set[str] = set()
    for item in raw:
        if not isinstance(item, str) or not is_valid_scope(item):
            raise ValueError(f"Geçersiz kapsam: {item!r}")
        scopes.add(item)
    if not scopes:
        raise ValueError("En az bir kapsam gerekir.")
    return frozenset(scopes)


def allows(granted: frozenset[str], required: str) -> bool:
    """İstenen kapsam verilenler arasında mı? (Üst kapsam alt kapsamı örtmez: açık liste.)"""
    return required in granted
