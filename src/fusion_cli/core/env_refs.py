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


#: Uzak sunucunun `url`/`headers` alanlarında BOŞ okunan kimlik bilgisi değişkenleri
#: (Claude Code "Credential variables that read as empty"; #244). Fusion'ın kendi sağlayıcı
#: anahtarları da "istemcinin kendi kimlik bilgisi" sayılır.
REMOTE_BLANKED_VARIABLES = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_CUSTOM_HEADERS",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "AWS_BEARER_TOKEN_BEDROCK",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "ALL_PROXY",
        "https_proxy",
        "http_proxy",
        "all_proxy",
        "NPM_TOKEN",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "NVIDIA_API_KEY",
        "NVIDIA_NIM_API_KEY",
        "OPENROUTER_API_KEY",
        "GROQ_API_KEY",
        "MISTRAL_API_KEY",
        "DEEPSEEK_API_KEY",
        "XAI_API_KEY",
    }
)


def expand_claude_refs(
    text: str, environ: Mapping[str, str], *, blanked: frozenset[str] = frozenset()
) -> tuple[str, tuple[str, ...]]:
    """Claude Code `.mcp.json` genişletmesi → (metin, eksik adlar) (#243, #244).

    - Tanımlı değişken (BOŞ metin dahil) değerine açılır; `${VAR:-x}` boşa açılır.
    - Tanımsız ve varsayılanlı başvuru varsayılana açılır.
    - Tanımsız ve varsayılansız başvuru `${VAR}` olarak KALIR ve eksik listesine girer.
    - `blanked` adlar tanımlı olsa da boş okunur, varsayılanları yok sayılır.
    """
    missing: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        name = match.group("name")
        if name in blanked:
            return ""
        if name in environ:
            value = environ[name]
            if name.endswith("_BASE_URL") and "@" in value.split("//", 1)[-1].split("/", 1)[0]:
                return ""  # adres kullanıcı adı/parola taşıyor: kimlik bilgisi sayılır
            return value
        default = match.group("default")
        if default is not None:
            return default
        missing.append(name)
        return match.group(0)

    return _REFERENCE.sub(_replace, text), tuple(dict.fromkeys(missing))
