"""Bir işlemin kimin adına, hangi çalışma alanında yürüdüğü (WP02).

Bağlam DEĞİŞMEZDİR ve yalnız kimlik/üyelik çözümleyicisi (`accounts.workspaces`)
tarafından kurulur. Ağdan, istek gövdesinden ya da modelin argümanlarından gelen
`tenant_id`/`workspace_id` doğrudan bu tipe çevrilmez: yetki çağıranın beyanı değil,
doğrulanmış kimliğin sonucudur.

Pilot varsayımı (plan §2): her hesap kendi kişisel tenant'ı ve tek sahipli
workspace'idir; ekip üyeliği ve paylaşılan kimlik bilgisi kapalı başlar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

#: Yerel sahibin (masaüstü kullanıcısı) kendi tenant'ında her işlemi yapabilmesi.
#: Tenant ve workspace sınırını AŞMAZ; yalnız kapsam denetimini geçer.
FULL_ACCESS = "*"

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


def validate_identifier(value: str, label: str) -> str:
    """Kimlik alanı boş değil, yol kaçışı içermiyor ve sınırlı uzunlukta mı?"""
    if not _SAFE_ID.match(value) or ".." in value:
        raise ValueError(f"Geçersiz {label}: {value!r}")
    return value


@dataclass(frozen=True, slots=True)
class Identity:
    """Doğrulanmış bir kişi: yerel hesap ya da o hesaba eşleşmiş cihaz."""

    user_id: str
    tenant_id: str
    scopes: frozenset[str] = field(default_factory=frozenset)
    device_id: str = ""


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    """Yürütme sınırı: kaynak erişimi ve veri kökü bu bağlamdan türetilir."""

    tenant_id: str
    user_id: str
    workspace_id: str
    device_id: str = ""
    session_id: str = ""
    run_id: str = ""
    scopes: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        validate_identifier(self.tenant_id, "tenant")
        validate_identifier(self.user_id, "kullanıcı")
        validate_identifier(self.workspace_id, "çalışma alanı")
        for value, label in ((self.device_id, "cihaz"), (self.run_id, "görev")):
            if value:
                validate_identifier(value, label)

    def has_scope(self, scope: str) -> bool:
        return FULL_ACCESS in self.scopes or scope in self.scopes

    def with_run(self, run_id: str) -> ExecutionContext:
        """Aynı kimlikle belirli bir göreve daraltılmış yeni bağlam."""
        return replace(self, run_id=run_id)
