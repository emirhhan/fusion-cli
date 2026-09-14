"""Fusion'ın varsayılan alan kaydını kuran fabrika.

Modül seviyesinde kayıt TUTULMAZ; her çağrı yeni (ama eşit) bir değer üretir. Yeni
alan eklemek aşağıdaki demete bir adaptör eklemektir; motor dosyası değişmez.
"""

from __future__ import annotations

from .godot import godot_adapter
from .registry import DomainRegistry
from .web import web_adapter


def default_domain_registry() -> DomainRegistry:
    """Kayıtlı alanlar, eşleşme ve kapı sırasıyla."""
    return DomainRegistry((godot_adapter(), web_adapter()))
