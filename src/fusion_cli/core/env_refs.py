"""Yapılandırma metnindeki ortam değişkeni başvuruları: `${VAR}` ve `${VAR:-varsayılan}`.

Claude Code `.mcp.json` ve Codex yapılandırması bu sözdizimini kullanır; Fusion da MCP
sunucu komutunda, argümanlarında, adresinde ve ortam değerlerinde tanır (P-049).

Genişletme YALNIZ bağlantı kurulurken yapılır (`mcp_bridge/transport.py`): yapılandırma
nesnesi başvuruyu olduğu gibi taşır, böylece `fusion mcp add` config'i yeniden yazarken
çözülmüş sır diske sızmaz.

Varsayılanı olmayan ve ortamda bulunmayan başvuru hatadır: boş metinle sessizce devam
etmek kimliksiz ya da yanlış adrese giden bir istek üretir.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from .errors import FusionError

#: `${AD}` ya da `${AD:-varsayılan}`; ad POSIX ortam değişkeni adıdır.
_REFERENCE = re.compile(r"\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?::-(?P<default>[^}]*))?\}")


class EnvRefError(FusionError):
    """Varsayılanı olmayan bir `${VAR}` başvurusu ortamda bulunamadı."""


def has_env_refs(text: str) -> bool:
    """Metin en az bir `${VAR}` başvurusu taşıyor mu?"""
    return _REFERENCE.search(text) is not None


def expand_env_refs(text: str, environ: Mapping[str, str]) -> str:
    """`${VAR}` / `${VAR:-varsayılan}` başvurularını `environ` ile çöz.

    Ortamda boş metin olan değişken "yok" sayılır (kabuk `:-` davranışı). Başvurusuz
    metin aynen döner.
    """

    def _replace(match: re.Match[str]) -> str:
        name = match.group("name")
        value = environ.get(name, "")
        if value:
            return value
        default = match.group("default")
        if default is not None:
            return default
        raise EnvRefError(
            f"Ortam değişkeni bulunamadı: {name} (yapılandırmada ${{{name}}} başvurusu var; "
            f"değişkeni tanımla ya da ${{{name}:-varsayılan}} yaz)"
        )

    return _REFERENCE.sub(_replace, text)


def referenced_names(text: str) -> tuple[str, ...]:
    """Metindeki başvurulan değişken adları (sırayla, tekrarsız)."""
    return tuple(dict.fromkeys(match.group("name") for match in _REFERENCE.finditer(text)))


def missing_refs(text: str, environ: Mapping[str, str]) -> tuple[str, ...]:
    """Varsayılanı olmayan ve ortamda TANIMLI olmayan başvurular (`claude mcp list` uyarısı)."""
    return tuple(
        dict.fromkeys(
            match.group("name")
            for match in _REFERENCE.finditer(text)
            if match.group("default") is None and match.group("name") not in environ
        )
    )
