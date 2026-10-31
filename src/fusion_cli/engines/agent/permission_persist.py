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
from ...config.permission_rules import PermissionDecision, PermissionRule, format_rule
from ...core.tools import ToolFamily, tool_family
from ...tools.auto_policy import command_words
from ...tools.write_targets import FILE_WRITE_TOOLS
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


def _shell_prefix(command: str) -> str:
    """`git status --short` → `git status *`; zincir ya da tek sözcükte birebir komut."""
    words = command_words(command)
    if len(words) != 1:
        return command
    parts = words[0]
    head = [token for token in parts[:3] if not token.startswith("-")]
    if len(head) < 2 or head != parts[: len(head)]:
        return " ".join(parts[:1]) + " *" if len(parts) > 1 else command
    return " ".join(head[:2]) + " *"


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


def remember_always(root: Path, request: ApprovalRequest) -> str:
    """Kuralı kalıcı yaz ve kullanıcıya gösterilecek özeti döndür.

    Proje dosyasına yazıldığında güven karması tazelenir (`permission_admin`); yazma
    hatası `ConfigError` olarak yükselir (çağıran kullanıcıya söyler, tur düşmez).
    """
    change = add_permission_rule(root, rule_for_request(request, root))
    return f"{format_rule(change.rule)} → {change.path}"
