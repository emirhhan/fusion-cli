"""Kabuk ve dosya yazma onay isteklerinin yardımcıları (`approval.py`'den ayrıldı)."""

from __future__ import annotations

from collections.abc import Collection
from pathlib import Path
from typing import TYPE_CHECKING

from ...config.permission_rules import PermissionRuleSet
from ...config.permissions import is_allowed
from ...core.tools import Tool, ToolArgs, ToolEffect
from ...tools.auto_policy import auto_risk, is_read_only_command
from ...tools.command_paths import escapes_project
from ...tools.command_policy import is_unattended_safe
from ...tools.delete_preview import delete_caution, describe_delete, script_danger
from ...tools.permission_match import writes_files
from ...tools.protected_paths import protected_path_reason
from ...tools.safe_delete import simple_rm_targets
from ...tools.safety import TRASHABLE_DELETE_REASONS, danger_reason
from ...tools.script_chain import script_chain_risk
from ...tools.write_targets import write_targets

if TYPE_CHECKING:
    from .approval import ApprovalRequest

#: Kök-dışı yazma engeli açıkken (P-002) modele dönen gerekçe.
OUTSIDE_WRITE_BLOCKED = (
    "proje kökü dışına yazma kapalı (ayar: runtime.block_writes_outside_root): {yol}. "
    "Gerekiyorsa kullanıcı `--add-dir <dizin>` ile ya da Ayarlar › İzinler'den açar"
)


def _outside_write_dir(
    tool: Tool, args: ToolArgs, root: Path | None, extra_roots: tuple[Path, ...]
) -> str | None:
    """Dosya yazma aracının hedefi kök (+ `--add-dir`) dışındaysa hedefin dizini.

    Yazan araç listesi `write_targets` ile ortaktır (A1-06, P-002): `download_file`,
    `extract_archive` ve görsel araçları da proje dışına yazıyorsa sorulur.
    """
    if root is None:
        return None
    targets = write_targets(tool.name, args)
    if not targets:
        return None
    raw = targets[0]
    try:
        path = Path(raw).expanduser()
        target = (path if path.is_absolute() else root / path).resolve()
        allowed = (root.resolve(), *(extra.resolve() for extra in extra_roots))
    except (OSError, RuntimeError, ValueError):
        # Çözümlenemeyen yol güvenli tarafta DIŞARIDA sayılır.
        return str(raw)
    if any(target == base or base in target.parents for base in allowed):
        return None
    return str(target.parent)


def _shell_request(
    tool: Tool,
    args: ToolArgs,
    command: str,
    allowed_commands: frozenset[str],
    effect: ToolEffect,
    root: Path | None,
    touched: Collection[Path] = (),
    *,
    rules: PermissionRuleSet | None = None,
) -> ApprovalRequest:
    """Kabuk komutunun onay isteği: kart komutu değil SONUCU göstermeli.

    Kök-dışı yazma engeli (P-002) kabuk yönlendirmesini de kapatır: `echo x > ~/.zshrc`,
    `| tee /etc/hosts`. Ölçüldü (31 Ekim): engel yalnız dosya araçlarında uygulanıyordu;
    Ayarlar'daki "onay bile sorulmadan engellenir" sözü kabukta tutmuyordu.
    """
    danger = danger_reason(tool.name, args)
    trashed = simple_rm_targets(command) is not None
    if trashed and danger in TRASHABLE_DELETE_REASONS:
        # Sade `rm` kalıcı silmez, Fusion çöpüne taşır (`shell._guarded_delete`).
        danger = None
    home = Path.home()
    if danger is None and root is not None:
        danger = script_danger(command, root, home)
    protected = protected_path_reason(tool.name, args, root, is_shell=True)
    danger = danger or protected
    caution = delete_caution(command, root, home) if root is not None else None
    target = describe_delete(command, root, home) if root is not None else ""
    chain = script_chain_risk(command, root, touched)
    risk = caution or auto_risk(command, root) or chain
    if danger is not None and target:
        danger = f"{danger}. {target}"
    note = ". ".join(part for part in (risk, target) if part) or None
    from .approval import ApprovalRequest

    pre_denied = None
    if rules is not None and rules.block_writes_outside_root and root is not None:
        disari = _outside_write_targets(command, root)
        if disari:
            pre_denied = OUTSIDE_WRITE_BLOCKED.format(yol=disari[0])
    return ApprovalRequest(
        tool=tool,
        args=args,
        danger=danger,
        # Tek kural motoru (#86): kural kümesi varsa Bash allow kararını yalnız
        # `permission_match.evaluate` verir; eski birebir liste yalnız kuralsız çağıranda.
        pre_allowed=rules is None and is_allowed(command, allowed_commands),
        unattended_safe=(trashed and caution is None)
        or (chain is None and is_unattended_safe(command, root)),
        effect=effect,
        risk=risk,
        read_only=is_read_only_command(command),
        note=note,
        pre_denied=pre_denied,
        protected=protected,
    )


def _outside_write_targets(command: str, root: Path) -> tuple[str, ...]:
    """Komutun yönlendirme/`tee` ile proje kökü DIŞINA yazdığı hedefler.

    Bilinmeyen değişken (`> $OUT`) dışarı sayılmaz (`auto_policy._outside` ile aynı kural);
    `$HOME`/`~` ve mutlak/`..` yollar sayılır.
    """
    return tuple(
        target
        for target in writes_files(command)
        if ("$" not in target or "$HOME" in target or "${HOME" in target)
        and escapes_project("tee", [target], root)
    )
