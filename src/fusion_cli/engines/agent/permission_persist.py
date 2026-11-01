"""Onay kartındaki "bir daha sorma" kararını KALICI izin kuralına çevirme (P-003).

Claude Code "Yes, and don't ask again for `git status`" dediğinde
`.claude/settings.local.json` `permissions.allow` listesine `Bash(git status:*)` yazar;
Fusion aynı dosyayı ve aynı biçimi kullanır — iki araçta tek liste.

Hedef dosya Claude gibi her zaman git kökündeki `.claude/settings.local.json`'dır (#68).
Dosya güveniliyorsa (ya da henüz yoksa) güven kaydındaki karma tazelenir (Fusion'ın kendi
yazdığı dosya bir sonraki turda "güvenilmiyor" diye düşmesin); güvenilmiyorsa kural yazılır
ama klasöre güvenilene dek bekletilir. Kural her zaman DAR üretilir: kabukta komutun
seçenek öncesi sözcükleri (`Bash(git status *)`), dosyada hedefin dizini
(`Edit(/src/alt/**)`), ötekilerde araç adı.
"""

from __future__ import annotations

from pathlib import Path

from ...config.local_settings_location import local_settings_path
from ...config.permission_admin import add_permission_rule
from ...config.permission_rules import PermissionDecision, PermissionRule, format_rule
from ...config.trust import is_permissions_trusted
from ...core.tools import ToolFamily, tool_family
from ...tools.auto_policy import command_words, is_read_only_command
from ...tools.bash_allow import allow_segments
from ...tools.write_targets import FILE_WRITE_TOOLS
from ...ui import messages
from .approval import ApprovalRequest
from .web_approval import web_rule

#: Zincirli komutta kaydedilen en çok kural (Claude, #68).
MAX_COMPOUND_RULES = 5


def rules_for_request(request: ApprovalRequest, root: Path | None) -> tuple[PermissionRule, ...]:
    """Kalıcı kurallar: zincirli kabuk komutunda onay gereken her alt komut için ayrı (en çok 5).

    Claude (#68): `git status && npm test` onaylanınca yalnız `npm test` için kural yazılır;
    salt okunur alt komut zaten sorulmaz.
    """
    if tool_family(request.tool.name) is not ToolFamily.SHELL:
        return (rule_for_request(request, root),)
    command = str(request.args.get("command", "")).strip()
    segments = allow_segments(command) or [command]
    if len(segments) < 2:
        return (rule_for_request(request, root),)
    needing = [seg for seg in segments if not is_read_only_command(seg)] or segments[:1]
    rules = [
        PermissionRule("Bash", _shell_prefix(seg), PermissionDecision.ALLOW) for seg in needing
    ]
    return tuple(dict.fromkeys(rules))[:MAX_COMPOUND_RULES]


def rule_for_request(request: ApprovalRequest, root: Path | None) -> PermissionRule:
    """İsteğe karşılık gelen EN DAR kalıcı izin kuralı."""
    tool = request.tool.name
    if tool_family(tool) is ToolFamily.SHELL:
        command = str(request.args.get("command", "")).strip()
        return PermissionRule("Bash", _shell_prefix(command), PermissionDecision.ALLOW)
    web = web_rule(request)
    if web is not None:
        # `WebFetch(domain:<alan>)` / `WebSearch` (#55).
        return web
    if tool in FILE_WRITE_TOOLS:
        raw = request.args.get("path")
        if isinstance(raw, str) and raw.strip():
            return PermissionRule("Edit", _dir_glob(raw, root), PermissionDecision.ALLOW)
    return PermissionRule(tool, None, PermissionDecision.ALLOW)


#: Verilen her şeyi çalıştıran yorumlayıcı ve başlatıcılar: `x *` kuralı sınırsız izin olur.
_LAUNCHERS = frozenset(
    {"python", "python3", "bash", "sh", "zsh", "node", "deno", "bun", "perl", "ruby", "php",
     "osascript", "find", "xargs", "eval", "exec", "env", "sudo", "doas", "timeout", "nohup",
     "npx", "uvx", "bunx", "pnpx", "ssh", "curl", "wget", "docker", "make"}
)  # fmt: skip


def _shell_prefix(command: str) -> str:
    """`git status --short` → `git status *`; zincir, yorumlayıcı ya da bayraklı komutta birebir.

    Ölçüldü (31 Ekim): ilk üç sözcükte bayrak varsa `ilk_sözcük *` kuralına düşülüyordu;
    `python -m pytest` için yazılan `Bash(python *)` her projede `python -c '…'` dahil
    sınırsız izin demekti. Artık yorumlayıcı/başlatıcıda ve ilk iki sözcüğü düz olmayan
    komutta kural komutun kendisidir (birebir); yalnız `a b [bayraklar]` biçimi `a b *` olur.
    """
    words = command_words(command)
    if len(words) != 1:
        return command
    parts = words[0]
    name = parts[0].rsplit("/", 1)[-1]
    if name in _LAUNCHERS or len(parts) < 2 or any(t.startswith("-") for t in parts[:2]):
        return command
    return " ".join(parts[:2]) + " *"


def _dir_glob(raw: str, root: Path | None) -> str:
    """Hedef dosyanın dizini: proje içinde `/dizin/**`, dışında `//mutlak/dizin/**`."""
    path = Path(raw).expanduser()
    base = root or Path.cwd()
    absolute = path if path.is_absolute() else base / path
    try:
        relative = absolute.resolve().parent.relative_to(base.resolve())
        inside = relative.as_posix()
        return f"/{inside}/**" if inside not in ("", ".") else "/**"
    except (ValueError, OSError, RuntimeError):
        return f"/{absolute.parent.as_posix()}/**"


def persist_target(root: Path) -> Path:
    """Kuralın yazılacağı dosya: Claude gibi her zaman yerel ayar dosyası (#68)."""
    return local_settings_path(root)


def always_description(request: ApprovalRequest, root: Path | None) -> str:
    """Onay kartındaki "bir daha sorma" seçeneğinin açıklaması: kural + KAPSAM.

    Ölçüldü (31 Ekim): proje izin dosyası güvenilmiyorken kural sessizce kullanıcının
    `permissions.json`'ına düşüyor, kart yalnız 'her oturumda geçerli olur' diyordu; kullanıcı
    'bu proje' sanıp tüm projelere izin yazıyordu. Hedef kullanıcı dosyasıysa açıkça söylenir.
    """
    rule = ", ".join(r.pattern for r in rules_for_request(request, root))
    if root is not None and not is_permissions_trusted(root):
        return messages.TUI_APPROVAL_ALWAYS_DESC_HELD.format(rule=rule, path=persist_target(root))
    return messages.TUI_APPROVAL_ALWAYS_DESC.format(rule=rule)


def remember_always(root: Path, request: ApprovalRequest) -> str:
    """Kuralı kalıcı yaz ve kullanıcıya gösterilecek özeti döndür.

    Proje dosyasına yazıldığında güven karması tazelenir (`permission_admin`); yazma
    hatası `ConfigError` olarak yükselir (çağıran kullanıcıya söyler, tur düşmez).
    """
    changes = [
        add_permission_rule(root, rule, local_only=True)
        for rule in rules_for_request(request, root)
    ]
    rules = ", ".join(format_rule(change.rule) for change in changes)
    return f"{rules} → {changes[0].path}"
