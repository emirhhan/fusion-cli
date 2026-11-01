"""Pazar girdisinin `archive`, `npm` ve `command` eklenti kaynakları (#399) — saf ayrıştırma.

Claude Code (marketplace-reference "Plugin sources"; kurallar Claude Code 2.1.287 şemasından):
- `archive`: `url` https zip (eklenti kökü arşivin tepesinde ya da tek sarmalayıcı klasörde),
  isteğe bağlı `sha256` (64 hex; her indirme doğrulanır, sürüm kimliği olarak ilk 12 karakter).
  Girdinin `headers` / `headersHelper`'ı yalnız bu kaynağa uygulanır; `headersHelper` girdinin
  `strict: false` olmasını ister.
- `npm`: `package` (ad, url ya da yerel yol; `..` parçası yok), `version` (sürüm/aralık),
  `registry` (http(s)).
- `command`: stdout'a eklenti klasörünün mutlak yolunu (tek satır) basan kabuk komutu; en çok
  500 yazdırılabilir ASCII karakter, 4+ boşluk dizisi yok; `timeout` 1-600 sn (varsayılan 60),
  `mode` `copy` (varsayılan) | `link`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from .plugins import PluginError

COMMAND_MAX_CHARS = 500
COMMAND_DEFAULT_TIMEOUT_S = 60
COMMAND_MAX_TIMEOUT_S = 600
_PRINTABLE = re.compile(r"[^\x20-\x7E]| {4,}")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_URLISH = re.compile(r"^(?:file|https?|git(?:\+https?|\+ssh)?|ssh|github|gitlab|bitbucket):", re.I)

ERR_ARCHIVE_URL = (
    "'{name}' archive url'i https:// olmalı ve loopback, link-local ya da bulut meta veri "
    "adresine gidemez: {value!r}"
)
ERR_ARCHIVE_SHA = "'{name}' sha256 64 karakterlik onaltılık SHA-256 özeti olmalı: {value!r}"
ERR_NPM_PACKAGE = "'{name}' npm package geçersiz (boş ya da '..' parçalı): {value!r}"
ERR_NPM_REGISTRY = "'{name}' npm registry http(s) adresi olmalı: {value!r}"
ERR_COMMAND = "'{name}' command 1-500 yazdırılabilir ASCII karakter olmalı (4+ boşluk dizisi yok)"
ERR_TIMEOUT = "'{name}' timeout 1-600 arası tam sayı (saniye) olmalı: {value!r}"
ERR_MODE = "'{name}' mode 'copy' ya da 'link' olmalı: {value!r}"
ERR_HELPER_STRICT = (
    'Plugin "{name}" sets headersHelper but is not "strict": false. An entry with '
    "headersHelper must inline its full manifest (strict: false) so users can review what it "
    "ships before the command runs."
)
WARN_HEADERS_UNUSED = (
    'Plugin "{name}" sets headers/headersHelper, which only apply to "archive" sources; they '
    "have no effect on this entry."
)
WARN_NO_PIN = (
    'Plugin "{name}" fetches its archive with a headersHelper but sets no sha256 pin. Consider '
    "pinning the digest so the bytes users install are exactly the ones you reviewed."
)

#: Kaynak seçeneklerinde başlık anahtarlarının öneki.
HEADER_PREFIX = "header:"
_BLOCKED_HOSTS = ("localhost", "metadata.google.internal", "metadata")


def _text(raw: Mapping[str, object], key: str) -> str:
    value = raw.get(key)
    return value.strip() if isinstance(value, str) else ""


def archive_url_allowed(url: str) -> bool:
    """https ve loopback/link-local/meta veri olmayan ana makine (Claude `Tnr`)."""
    from ipaddress import ip_address
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
    except ValueError:
        return False
    if parts.scheme != "https" or not host or host in _BLOCKED_HOSTS:
        return False
    try:
        address = ip_address(host)
    except ValueError:
        return not host.endswith(".localhost")
    return not (address.is_loopback or address.is_link_local or address.is_unspecified)


def archive_options(
    raw: Mapping[str, object], entry: Mapping[str, object], name: str
) -> tuple[str, tuple[tuple[str, str], ...], tuple[str, ...]]:
    """(url, seçenekler, uyarılar); seçenekler `sha256`, `header:<ad>`, `headersHelper`."""
    url = _text(raw, "url")
    if not archive_url_allowed(url):
        raise PluginError(ERR_ARCHIVE_URL.format(name=name, value=raw.get("url")))
    sha = _text(raw, "sha256")
    if sha and not _SHA256.match(sha):
        raise PluginError(ERR_ARCHIVE_SHA.format(name=name, value=sha))
    options: list[tuple[str, str]] = [("sha256", sha.lower())] if sha else []
    headers = entry.get("headers")
    if isinstance(headers, Mapping):
        options += [
            (f"{HEADER_PREFIX}{k}", str(v)) for k, v in headers.items() if isinstance(v, str)
        ]
    helper = _text(entry, "headersHelper")
    notes: tuple[str, ...] = ()
    if helper:
        if entry.get("strict") is not False:
            raise PluginError(ERR_HELPER_STRICT.format(name=name))
        options.append(("headersHelper", helper))
        notes = () if sha else (WARN_NO_PIN.format(name=name),)
    return url, tuple(options), notes


def npm_options(
    raw: Mapping[str, object], name: str
) -> tuple[str, str, tuple[tuple[str, str], ...]]:
    """(package, version, seçenekler)."""
    package = _text(raw, "package")
    if not package or (not _URLISH.match(package) and ".." in package.split("/")):
        raise PluginError(ERR_NPM_PACKAGE.format(name=name, value=raw.get("package")))
    registry = _text(raw, "registry")
    if registry and not re.match(r"^https?://[^/\s]+", registry):
        raise PluginError(ERR_NPM_REGISTRY.format(name=name, value=registry))
    return package, _text(raw, "version"), ((("registry", registry),) if registry else ())


def command_options(
    raw: Mapping[str, object], name: str
) -> tuple[str, tuple[tuple[str, str], ...]]:
    """(komut, seçenekler `timeout`, `mode`)."""
    command = raw.get("command")
    valid = isinstance(command, str) and 0 < len(command) <= COMMAND_MAX_CHARS
    if not valid or _PRINTABLE.search(str(command)):
        raise PluginError(ERR_COMMAND.format(name=name))
    timeout = raw.get("timeout", COMMAND_DEFAULT_TIMEOUT_S)
    if (
        not isinstance(timeout, int)
        or isinstance(timeout, bool)
        or not 0 < timeout <= COMMAND_MAX_TIMEOUT_S
    ):
        raise PluginError(ERR_TIMEOUT.format(name=name, value=timeout))
    mode = raw.get("mode", "copy")
    if mode not in ("copy", "link"):
        raise PluginError(ERR_MODE.format(name=name, value=mode))
    return str(command), (("timeout", str(timeout)), ("mode", str(mode)))


def headers_warning(raw: Mapping[str, object], kind: str, name: str) -> tuple[str, ...]:
    """`headers`/`headersHelper` archive dışı girdide etkisizdir (Claude uyarısı)."""
    if kind != "archive" and ("headers" in raw or "headersHelper" in raw):
        return (WARN_HEADERS_UNUSED.format(name=name),)
    return ()
