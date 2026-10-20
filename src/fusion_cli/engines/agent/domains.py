"""Alan adaptörleri için geriye uyumlu giriş noktası.

Sözleşme, kayıt defteri ve alan paketleri `domain_adapters` paketindedir. Bu modül
yalnız mevcut içe aktarmaların (`domains.godot_adapter` vb.) çalışmaya devam etmesi
için adları yeniden dışa açar; yeni kod doğrudan `domain_adapters` paketini kullanır.
"""

from __future__ import annotations

from pathlib import Path

from .domain_adapters.contract import DomainAdapter
from .domain_adapters.defaults import default_domain_registry
from .domain_adapters.godot import godot_adapter, godot_has_main_scene, godot_needs_import
from .domain_adapters.web import web_adapter

__all__ = [
    "DomainAdapter",
    "adapter_for",
    "godot_adapter",
    "godot_has_main_scene",
    "godot_needs_import",
    "web_adapter",
]


def adapter_for(root: Path) -> DomainAdapter | None:
    """Bu proje varsayılan kayıttaki bir alana ait mi? Değilse `None`."""
    return default_domain_registry().first_match(root)
