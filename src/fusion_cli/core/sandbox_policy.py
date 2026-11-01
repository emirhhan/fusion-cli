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
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "NETWORK_ALLOWLIST",
    "NETWORK_MODES",
    "NETWORK_OPEN",
    "PROTECTED_ANCHORS",
    "PROTECTED_WRITE_PATHS",
    "SandboxHostGate",
    "SandboxPolicy",
    "domain_allowed",
    "domain_denied",
    "normalize_domain",
    "protected_anchors",
    "protected_write_paths",
    "read_rules",
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


@dataclass(frozen=True, slots=True)
class SandboxPolicy:
    """Sandbox açıkken uygulanacak kurallar; varsayılanlar eski `write_root` davranışıdır."""

    #: Kök (+ `--add-dir`) ve geçici dizinlere EK yazılabilir dizinler.
    extra_write: tuple[Path, ...] = ()
    #: Yazılabilir bölgelerin içinde de yazılamayan yollar (Claude `filesystem.denyWrite`, #350).
    deny_write: tuple[Path, ...] = ()
    #: Sandbox içinde okunamayan yollar (dizin ise altı da).
    deny_read: tuple[Path, ...] = ()
    #: `deny_read` bölgesinin içini yeniden açan yollar (Claude `allowRead`; dar olan kazanır).
    allow_read: tuple[Path, ...] = ()
    #: `allow_read` ile açılamayan engeller (Fusion'ın kendi sır dosyaları).
    locked_read: tuple[Path, ...] = ()
    #: `open` | `allowlist`.
    network: str = NETWORK_ALLOWLIST
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
    #: Sandbox içindeki komutlar onaysız çalışır (Claude `autoAllowBashIfSandboxed`; yıkıcı,
    #: deny/ask kuralı ve plan kipi hariç). Claude'da varsayılan açık (#347).
    auto_allow: bool = True
    #: Sandbox içindeki komutun ortamından sır gibi görünen değişkenler (`*_TOKEN`…) çıkarılır.
    hide_secret_env: bool = False
    #: Sandbox ortamından her zaman çıkarılan adlar (Claude `credentials.envVars` deny, #368).
    deny_env: tuple[str, ...] = ()
    #: Her kipte kapalı loopback portları: Fusion Chrome'larının CDP portu (çalışma anında
    #: `tools.sandbox_cdp` doldurur; yapılandırmadan gelmez). Yalnız macOS Seatbelt uygular.
    denied_local_ports: tuple[int, ...] = ()
    #: Listede olmayan ana makineye sormadan reddet (Claude `network.strictAllowlist`, #323).
    strict_allowlist: bool = False

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


def domain_denied(host: str, policy: SandboxPolicy) -> bool:
    """Ad `deniedDomains`'te mi (ya da geçersiz mi)? Her kipte reddedilir."""
    normalized = normalize_domain(host)
    if normalized is None:
        return True
    return any(_matches(normalized, entry) for entry in policy.denied_domains)


@dataclass(slots=True)
class SandboxHostGate:
    """Listede olmayan ana makine için karar veren taraf (motor kurar; #323).

    `decider(host)` proxy thread'inden çağrılır ve True dönerse bağlantı geçer. `session_hosts`
    kullanıcının "Evet" dediği adları oturum boyunca tutar; `None` karar veren yok demektir
    (liste dışı ad reddedilir).
    """

    decider: Callable[[str], bool] | None = None
    session_hosts: set[str] = field(default_factory=set)


def domain_allowed(host: str, policy: SandboxPolicy) -> bool:
    """Proxy bu ana makineye bağlanabilir mi? Yasak listesi her zaman önce gelir."""
    normalized = normalize_domain(host)
    if normalized is None:
        return False
    if any(_matches(normalized, entry) for entry in policy.denied_domains):
        return False
    return any(_matches(normalized, entry) for entry in policy.allowed_domains)


def _under(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def read_rules(policy: SandboxPolicy) -> tuple[tuple[Path, bool], ...]:
    """Okuma kuralları uygulama sırasıyla: `(yol, izin_mi)`; SONRAKİ kural kazanır (#349).

    Claude (sandboxing, Filesystem): okuma kuralları çakışınca dar yol kazanır — `denyRead
    ["~/"]` + `allowRead ["~/projects"]` projeyi açar, `allowRead ["~/"]` + `denyRead
    ["~/.env"]` sırrı kapalı tutar. Geniş yol önce, dar yol sonra yazılır; aynı yolda engel
    kazanır. Yalnız bir engelin içindeki `allow_read` anlamlıdır (gerisi zaten okunur).
    `locked_read` en sona eklenir: hiçbir `allow_read` onu açamaz.
    """
    locked = tuple(dict.fromkeys(path.resolve() for path in policy.locked_read))
    denied = tuple(
        path
        for path in dict.fromkeys(item.resolve() for item in policy.deny_read)
        if path not in locked
    )
    opened = tuple(
        path
        for path in dict.fromkeys(item.resolve() for item in policy.allow_read)
        if any(_under(path, deny) for deny in denied)
    )
    ordered = sorted(
        [(path, True) for path in opened] + [(path, False) for path in denied],
        key=lambda item: (len(item[0].parts), not item[1]),
    )
    return (*ordered, *((path, False) for path in locked))


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
