"""Masaüstü paketinin kullanacağı hafif çalışma zamanı sağlık denetimi."""

from __future__ import annotations

import platform
import sys
from dataclasses import asdict, dataclass
from importlib.resources import files
from typing import Any

from . import __version__

_REQUIRED_RESOURCES = (
    "config/defaults.yaml",
    "engines/agent/prompts/system.md",
    "engines/agent/prompts/lessons.txt",
    "engines/fusion/prompts/judge.txt",
    "gateway/dashboard.html",
)


def _tokenizer_plugins_ok() -> bool:
    """LiteLLM'in paket dışı namespace encoding eklentisini doğrula."""
    try:
        import tiktoken

        return tiktoken.get_encoding("cl100k_base").name == "cl100k_base"
    except (ImportError, ValueError):
        return False


@dataclass(frozen=True)
class RuntimeHealth:
    """Paketlenmiş çalışma zamanının bütünlük anlık görüntüsü."""

    version: str
    python: str
    platform: str
    resources_ok: bool

    def to_dict(self) -> dict[str, Any]:
        """JSON çıktısı için sözlük gösterimini üret."""
        return {"ok": self.resources_ok, **asdict(self)}


def collect_runtime_health() -> RuntimeHealth:
    """Ağ ya da model çağırmadan paket sürümünü ve zorunlu kaynakları doğrula."""
    root = files("fusion_cli")
    resources_ok = _tokenizer_plugins_ok() and all(
        root.joinpath(*relative.split("/")).is_file() for relative in _REQUIRED_RESOURCES
    )
    return RuntimeHealth(
        version=__version__,
        python=platform.python_version(),
        platform=f"{sys.platform}-{platform.machine()}",
        resources_ok=resources_ok,
    )
