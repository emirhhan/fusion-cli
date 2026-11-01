"""`plugin marketplace add <kaynak>` kaynak biçimleri (Claude Code kaynak tablosu, #395).

Desteklenen: `owner/repo`, `owner/repo#ref`, `owner/repo@ref` (GitHub); `.git` ile biten ya da
`/_git/` içeren https adresi; github.com/gitlab.com https adresi (git olarak klonlanır);
`./`, `../`, `/`, `~` ile başlayan klasör (directory) ya da `.json` dosyası (file).

Fusion'da açıkça desteklenmeyen (Claude'da var): SSH (`user@host:path`), düz `http://`, ve
`.git`'siz başka https adresinin marketplace.json olarak indirilmesi (url türü). Fusion klonu yalnız
genel https adresleriyle, iç ağa çıkmadan yapar; bunlar açık hata mesajıyla reddedilir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from ..core.plugins import PluginError

KIND_DIRECTORY = "yerel"
KIND_FILE = "dosya"
KIND_GIT = "git"
OFFICIAL_ALIAS = "resmi"
OFFICIAL_MARKETPLACE = "https://github.com/anthropics/claude-plugins-official"
#: Claude: `Invalid marketplace source format. Try: owner/repo, https://..., or ./path`
ERR_FORMAT = "Geçersiz pazar kaynağı biçimi. Dene: owner/repo, https://... ya da ./yol"
ERR_BARE_HOST = (
    "'{spec}' geçersiz owner/repo kısaltması: başına https:// ekle ya da yerel yol kullan"
)
ERR_SSH = "SSH pazar kaynakları (user@host:path) Fusion'da desteklenmiyor; https adresi kullan"
ERR_HTTP = "Yalnız https adresleri kabul edilir: {spec}"
ERR_URL_KIND = (
    "marketplace.json adresi (url türü) Fusion'da desteklenmiyor; depoyu klonlamak için "
    "adresin sonuna .git ekle: {spec}"
)
ERR_NOT_FOUND = "Pazar yolu bulunamadı: {spec}"

_SSH = re.compile(r"^[\w.-]+@[\w.-]+:.+")
_SHORTHAND = re.compile(r"^([A-Za-z0-9](?:[A-Za-z0-9-]*))/([A-Za-z0-9._-]+?)(?:[#@](.+))?$")
_GIT_HOSTS = frozenset({"github.com", "gitlab.com"})
_PATH_PREFIXES = ("./", "../", "/", "~")


@dataclass(frozen=True, slots=True)
class MarketSource:
    kind: str
    location: str
    ref: str = ""

    @property
    def record_source(self) -> str:
        """Kayıtta saklanan kaynak metni (`url#ref`); yeniden ekleme/güncelleme bunu kullanır."""
        return f"{self.location}#{self.ref}" if self.ref else self.location


def split_ref(source: str) -> tuple[str, str]:
    """Kayıttaki `url#ref` metnini (adres, ref) olarak ayır."""
    url, _, ref = source.partition("#")
    return url, ref


def parse_market_source(spec: str) -> MarketSource:
    """Kullanıcının yazdığı kaynağı türüne ayır; desteklenmeyen biçimde açık hata."""
    text = spec.strip()
    if text.lower() == OFFICIAL_ALIAS:
        return MarketSource(KIND_GIT, OFFICIAL_MARKETPLACE)
    local = Path(text).expanduser()
    if text.startswith(_PATH_PREFIXES) or (text and local.exists()):
        return _local(local, spec)
    if _SSH.match(text):
        raise PluginError(ERR_SSH)
    if text.startswith("http://"):
        raise PluginError(ERR_HTTP.format(spec=spec))
    if text.startswith("https://"):
        return _https(text, spec)
    match = _SHORTHAND.match(text)
    if match is None:
        head = text.split("/", 1)[0]
        raise PluginError(ERR_BARE_HOST.format(spec=spec) if "." in head else ERR_FORMAT)
    owner, repo, ref = match.groups()
    return MarketSource(KIND_GIT, f"https://github.com/{owner}/{repo}", ref or "")


def _local(path: Path, spec: str) -> MarketSource:
    if path.is_dir():
        return MarketSource(KIND_DIRECTORY, str(path.resolve()))
    if path.is_file() and path.suffix.lower() == ".json":
        return MarketSource(KIND_FILE, str(path.resolve()))
    raise PluginError(ERR_NOT_FOUND.format(spec=spec))


def _https(text: str, spec: str) -> MarketSource:
    url, _, ref = text.partition("#")
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if url.endswith(".git") or "/_git/" in parts.path:
        return MarketSource(KIND_GIT, url, ref)
    if host in _GIT_HOSTS:
        # Claude `.git` ekleyerek klonlar; git bunu kendisi de çözer, kayıt adresi değişmesin.
        return MarketSource(KIND_GIT, url.rstrip("/"), ref)
    raise PluginError(ERR_URL_KIND.format(spec=spec))


def market_root(kind: str, path: Path) -> Path:
    """Göreli eklenti yollarının çözüldüğü kök: file türünde dosyanın pazar klasörü."""
    if kind != KIND_FILE:
        return path
    parent = path.parent
    return parent.parent if parent.name == ".claude-plugin" else parent
