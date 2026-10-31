"""`run_shell` sandbox politikası: okuma engeli, ek yazma kökleri, ağ allowlist'i (P-010).

Claude Code `sandbox.*` (filesystem.allowWrite/denyRead, network.allowedDomains/
deniedDomains, failIfUnavailable, allowUnsandboxedCommands, excludedCommands,
autoAllowBashIfSandboxed) ve Codex `workspace-write` + ağ proxy'si davranışının Fusion
karşılığı. Kip anahtarı geri uyumlu olarak `runtime.shell_sandbox`'ta kalır; bu nesne
yalnız kip AÇIKKEN uygulanır. Yollar burada çözülmüş (mutlak) gelir; `~` açılımı config
katmanındadır.
"""

from __future__ import annotations

import ipaddress
import re
import shlex
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "NETWORK_ALLOWLIST",
    "NETWORK_MODES",
    "NETWORK_OPEN",
    "PROTECTED_ANCHORS",
    "PROTECTED_WRITE_PATHS",
    "SandboxPolicy",
    "domain_allowed",
    "is_excluded_command",
    "normalize_domain",
    "protected_anchors",
    "protected_write_paths",
]

#: Ağ kısıtı yok (eski davranış).
NETWORK_OPEN = "open"
#: Ağ yalnız Fusion'ın yerel proxy'si üzerinden, izinli alan adlarına açık.
NETWORK_ALLOWLIST = "allowlist"
NETWORK_MODES = (NETWORK_OPEN, NETWORK_ALLOWLIST)

#: Alan adı girdisi: `ornek.com`, `*.ornek.com`, `localhost` ya da IP.
_DOMAIN = re.compile(
    r"^(\*\.)?[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?)*$"
)
#: Yazılabilir kökün altında bile sandbox içinden YAZILAMAYAN yollar (köke göreli).
#:
#: Claude Code'un zorunlu deny-write listesi ve Codex'in `.git`'i salt okunur bağlaması
#: gibi: Fusion'ın sandbox'sız `git` aracı `.git/config`'teki `core.fsmonitor`'u ve
#: `.git/hooks`'u çalıştırır; ayar/launch/MCP dosyaları izin ve süreç başlatma taşır.
#: Ölçüldü (31 Ekim): sandbox içinden `.git/config`'e fsmonitor yazılıp `git status`
#: (salt okunur, sorusuz) çağrılınca komut sandbox DIŞINDA çalıştı.
PROTECTED_WRITE_PATHS: tuple[str, ...] = (
    ".git/config",
    ".git/config.worktree",
    ".git/hooks",
    ".claude/settings.json",
    ".claude/settings.local.json",
    ".claude/launch.json",
    ".fusion/launch.json",
    ".fusion/tools",
    ".mcp.json",
)
#: Korumalı yolları içeren dizinler: taşınamaz/silinemez (`mv .git x`, düzenle, geri taşı).
PROTECTED_ANCHORS: tuple[str, ...] = (".git", ".claude", ".fusion")
#: Bu işaretlerden biri olan komut bileşiktir; sandbox dışı listesiyle eşleşmez.
_COMPOUND_MARKERS = (";", "&", "|", "`", "$(", "\n", ">", "<")


@dataclass(frozen=True, slots=True)
class SandboxPolicy:
    """Sandbox açıkken uygulanacak kurallar; varsayılanlar eski `write_root` davranışıdır."""

    #: Kök (+ `--add-dir`) ve geçici dizinlere EK yazılabilir dizinler.
    extra_write: tuple[Path, ...] = ()
    #: Sandbox içinde okunamayan yollar (dizin ise altı da).
    deny_read: tuple[Path, ...] = ()
    #: `open` | `allowlist`.
    network: str = NETWORK_OPEN
    #: `allowlist` kipinde erişilebilen alan adları (`*.ornek.com` alt alan adları).
    allowed_domains: tuple[str, ...] = ()
    #: Her kipte reddedilen alan adları; izin listesinden üstündür.
    denied_domains: tuple[str, ...] = ()
    #: `allowlist` kipinde `localhost` (dev sunucusu, yerel veritabanı) açık mı?
    allow_localhost: bool = True
    #: Sandbox kurulamıyorsa (platform/araç yok) komut ÇALIŞTIRILMAZ.
    fail_if_unavailable: bool = False
    #: Model `unsandboxed=true` ile sandbox dışı çalıştırma isteyebilir mi (her seferinde onay)?
    allow_unsandboxed: bool = True
    #: Her zaman sandbox dışında çalışan komut önekleri (`docker`, `git push`).
    excluded_commands: tuple[str, ...] = ()
    #: Sandbox içinde ve ağ kısıtlıyken komutlar onaysız çalışır (yıkıcı/ask kuralı hariç).
    auto_allow: bool = False
    #: Sandbox içindeki komutun ortamından sır gibi görünen değişkenler (`*_TOKEN`…) çıkarılır.
    hide_secret_env: bool = True

    @property
    def restricts_network(self) -> bool:
        return self.network == NETWORK_ALLOWLIST


def normalize_domain(text: str) -> str | None:
    """Alan adı girdisini küçük harfe ve sondaki noktasız biçime getir; geçersizse None."""
    value = text.strip().lower().rstrip(".")
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value.strip("[]")))
    except ValueError:
        pass
    return value if _DOMAIN.match(value) else None


def _matches(host: str, entry: str) -> bool:
    if entry.startswith("*."):
        return host.endswith(entry[1:])
    return host == entry


def domain_allowed(host: str, policy: SandboxPolicy) -> bool:
    """Proxy bu ana makineye bağlanabilir mi? Yasak listesi her zaman önce gelir."""
    normalized = normalize_domain(host)
    if normalized is None:
        return False
    if any(_matches(normalized, entry) for entry in policy.denied_domains):
        return False
    return any(_matches(normalized, entry) for entry in policy.allowed_domains)


def is_excluded_command(command: str, patterns: tuple[str, ...]) -> bool:
    """Komut sandbox dışı listesindeki bir önekle mi başlıyor?

    Yalnız TEK ve sade komut eşleşir: `docker ps && curl …` gibi bileşik bir komut
    listede `docker` olsa bile sandbox içinde kalır; aksi hâlde önek, zincirin geri
    kalanını da sandbox dışına taşırdı.
    """
    if not patterns or any(marker in command for marker in _COMPOUND_MARKERS):
        return False
    try:
        words = shlex.split(command)
    except ValueError:
        return False
    for pattern in patterns:
        wanted = [word for word in pattern.split() if word != "*"]
        if wanted and words[: len(wanted)] == wanted:
            return True
    return False


def protected_write_paths(roots: Sequence[Path]) -> tuple[Path, ...]:
    """Köklerin altındaki korumalı yollar (var olmasalar da; macOS yolu yoksa da korur)."""
    return tuple(
        dict.fromkeys(root / relative for root in roots for relative in PROTECTED_WRITE_PATHS)
    )


def protected_anchors(roots: Sequence[Path]) -> tuple[Path, ...]:
    """Taşınması engellenen dizinler; kökün kendisi de (iç içe yazılabilir kökler için)."""
    return tuple(
        dict.fromkeys(
            path
            for root in roots
            for path in (root, *(root / anchor for anchor in PROTECTED_ANCHORS))
        )
    )
