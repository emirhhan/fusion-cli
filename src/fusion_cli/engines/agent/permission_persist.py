"""Onay kartındaki "bir daha sorma" kararını KALICI izin kuralına çevirme (P-003).

Claude Code "Yes, and don't ask again for `git status`" dediğinde
`.claude/settings.local.json` `permissions.allow` listesine `Bash(git status:*)` yazar;
Fusion aynı dosyayı ve aynı biçimi kullanır — iki araçta tek liste.

Hedef dosya: proje güveniliyorsa (ya da henüz izin dosyası yoksa) projenin
`.claude/settings.local.json`'ı ve güven kaydındaki karma tazelenir (Fusion'ın kendi
yazdığı dosya bir sonraki turda "güvenilmiyor" diye düşmesin); proje güvenilmiyorsa
kullanıcının `permissions.json`'ı. Kural her zaman DAR üretilir: kabukta komutun
seçenek öncesi sözcükleri (`Bash(git status *)`), dosyada hedefin dizini
(`Edit(/src/alt/**)`), ötekilerde araç adı.
"""

from __future__ import annotations

from pathlib import Path

from ...config.permission_admin import add_permission_rule, project_rule_file
from ...config.permission_rules import (
    PermissionDecision,
    PermissionRule,
    format_rule,
    user_permissions_file,
)
from ...core.tools import ToolFamily, tool_family
from ...tools.auto_policy import command_words
from ...tools.write_targets import FILE_WRITE_TOOLS
from ...ui import messages
from .approval import ApprovalRequest


def rule_for_request(request: ApprovalRequest, root: Path | None) -> PermissionRule:
    """İsteğe karşılık gelen EN DAR kalıcı izin kuralı."""
    tool = request.tool.name
    if tool_family(tool) is ToolFamily.SHELL:
        command = str(request.args.get("command", "")).strip()
        return PermissionRule("Bash", _shell_prefix(command), PermissionDecision.ALLOW)
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
    """Kuralın yazılacağı dosya: güvenilen projede yerel ayar, değilse kullanıcı dosyası."""
    return project_rule_file(root)


def always_description(request: ApprovalRequest, root: Path | None) -> str:
    """Onay kartındaki "bir daha sorma" seçeneğinin açıklaması: kural + KAPSAM.

    Ölçüldü (31 Ekim): proje izin dosyası güvenilmiyorken kural sessizce kullanıcının
    `permissions.json`'ına düşüyor, kart yalnız 'her oturumda geçerli olur' diyordu; kullanıcı
    'bu proje' sanıp tüm projelere izin yazıyordu. Hedef kullanıcı dosyasıysa açıkça söylenir.
    """
    rule = rule_for_request(request, root).pattern
    if root is not None and persist_target(root) == user_permissions_file():
        return messages.TUI_APPROVAL_ALWAYS_DESC_USER.format(
            rule=rule, path=user_permissions_file()
        )
    return messages.TUI_APPROVAL_ALWAYS_DESC.format(rule=rule)


def remember_always(root: Path, request: ApprovalRequest) -> str:
    """Kuralı kalıcı yaz ve kullanıcıya gösterilecek özeti döndür.

    Proje dosyasına yazıldığında güven karması tazelenir (`permission_admin`); yazma
    hatası `ConfigError` olarak yükselir (çağıran kullanıcıya söyler, tur düşmez).
    """
    change = add_permission_rule(root, rule_for_request(request, root))
    return f"{format_rule(change.rule)} → {change.path}"
