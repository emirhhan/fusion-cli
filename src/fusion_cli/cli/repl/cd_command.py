"""`/cd <yol>` — oturumun çalışma dizinini (proje kökünü) değiştir (P-072).

Claude Code `/cd` ve Codex `/cd` karşılığı. Konuşma aynı sohbettir: geçmiş,
checkpoint'ler ve zamanlanmış görevler korunur; araçlar sonraki turdan itibaren yeni
kökte çalışır. Kök kuralları:

- hedef var olan bir klasör olmalı; disk kökü ya da ev dizininin tamamı olamaz
  (`/add-dir` ile aynı sınır);
- kullanıcının izin kurallarındaki `Cd(<glob>)` DENY kuralı hedefi engeller
  (ör. `"deny": ["Cd(//etc/**)"]`);
- eski projenin ek klasörleri ve "oturum boyunca izin ver" kararları taşınmaz
  (`ReplState.rebind_root`); güvenilmeyen projede izin dosyası uyarısı gösterilir.

Model bir sonraki turda dizin değişikliğini bağlam notu olarak görür; `CwdChanged`
kancası (P-009, yük `{old_cwd, new_cwd}`) kuyruğa alınır ve komutu çalıştıran yüzey
(REPL, TUI, masaüstü) hemen gönderir (`hook_events.flush`). Proje `config.yaml`/`.mcp.json`
oturum açılışındaki dizinden okunmuştu ve yeniden yüklenmez (masaüstü kök değişimiyle aynı sınır).
"""

from __future__ import annotations

import os
from pathlib import Path

from ...config.permission_rules import PermissionDecision
from ...config.permissions import has_untrusted_permissions
from ...core.worktree import worktree_for_path
from ...tools.permission_match import CD_RULE_TOOL, evaluate
from ...ui import messages
from . import prefixes
from .state import ReplState


def cd_command(state: ReplState, argument: str) -> str:
    """`/cd` mevcut dizini söyler; `/cd <yol>` oturumu o klasöre taşır."""
    text = argument.strip().strip("\"'")
    if not text:
        return messages.CD_CURRENT.format(path=state.root)
    target = resolve_target(state.root, text)
    if target is None:
        return messages.CD_NOT_FOUND
    problem = target_problem(state, target, written=lexical_target(state.root, text))
    return problem or change_directory(state, target)


def resolve_target(root: Path, text: str) -> Path | None:
    """Göreli yol mevcut köke göre çözülür; `~` ev dizinidir. Çözülemezse None."""
    try:
        path = Path(text).expanduser()
        return (path if path.is_absolute() else root / path).resolve()
    except (OSError, RuntimeError):
        return None


def lexical_target(root: Path, text: str) -> Path | None:
    """Kullanıcının yazdığı yolun sembolik bağ çözülmemiş mutlak biçimi (`..` sözcüksel)."""
    try:
        path = Path(text).expanduser()
        return Path(os.path.normpath(path if path.is_absolute() else root / path))
    except (OSError, RuntimeError, ValueError):
        return None


def target_problem(state: ReplState, target: Path, *, written: Path | None = None) -> str:
    """Hedef kök kurallarına uymuyorsa kullanıcı metni; uyuyorsa boş.

    `Cd(...)` DENY kuralı hem çözülmüş hedefe hem kullanıcının yazdığı biçime (`written`)
    bakar. Ölçüldü (31 Ekim): yalnız çözülmüş yol değerlendirildiğinden macOS'ta
    `Cd(//etc/**)` kuralı `/cd /etc` (`/private/etc`) geçişini engellemiyordu.
    """
    if not target.is_dir():
        return messages.CD_NOT_FOUND
    if target == state.root.expanduser().resolve():
        return messages.CD_SAME.format(path=target)
    if target in (Path(target.anchor), Path.home().resolve()):
        return messages.CD_TOO_BROAD
    rules = state.permission_rules()
    for path in dict.fromkeys((target, written or target)):
        match = evaluate(rules, CD_RULE_TOOL, {"path": str(path)}, state.root)
        if match is not None and match.decision is PermissionDecision.DENY:
            return messages.CD_DENIED.format(rule=match.rule.pattern)
    # Claude (#81): herhangi bir `Cd` allow kuralı `/cd`'yi izin listesi kipine sokar.
    allows = [
        r for r in rules.rules if r.tool == CD_RULE_TOOL and r.decision is PermissionDecision.ALLOW
    ]
    if (
        allows
        and evaluate(rules.with_rules(allows), CD_RULE_TOOL, {"path": str(target)}, state.root)
        is None
    ):
        return messages.CD_NOT_ALLOWED.format(path=target)
    return ""


def change_directory(state: ReplState, target: Path) -> str:
    """Kökü değiştir, modele bağlam notu bırak ve kullanıcıya özet döndür."""
    previous = state.root.expanduser().resolve()
    left_worktree = state.worktree
    state.rebind_root(target)
    state.worktree = worktree_for_path(target)
    state.hooks().defer_cwd_changed(previous, target)
    prefixes.push_pending_context(state, messages.CD_CONTEXT_NOTE.format(old=previous, new=target))
    lines = [messages.CD_CHANGED.format(old=previous, new=target)]
    if left_worktree is not None and state.worktree != left_worktree:
        lines.append(messages.CD_WORKTREE_LEFT.format(path=left_worktree.path))
    if has_untrusted_permissions(target):
        lines.append(messages.PERMISSIONS_UNTRUSTED)
    return "\n".join(lines)
