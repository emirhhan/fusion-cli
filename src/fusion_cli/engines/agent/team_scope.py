"""Alt ajanların canonical dosya kapsamı ve dalga zamanlayıcısı."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from ...core.tools import ToolContext
from ...tools.files import writable_path

if TYPE_CHECKING:
    from .team import SubTask


def schedule_waves(subtasks: Sequence[SubTask]) -> list[list[int]]:
    """Görevleri birlikte koşabilecek dalgalara böl (sıra korunur).

    Kural: salt okuyan görev her dalgaya katılır; yazma alanı bildiren görev,
    dalgadaki alanlarla çakışmıyorsa katılır; alanı belirsiz yazan görev tek
    başına bir dalgadır (neye dokunacağı bilinmediği için kimseyle koşmaz).
    """
    waves: list[list[int]] = []
    current: list[int] = []
    claimed: list[Path] = []
    for index, subtask in enumerate(subtasks):
        if subtask.read_only:
            current.append(index)
            continue
        scope = [Path(raw).expanduser().resolve() for raw in subtask.write_scope]
        if scope and not any(_overlaps(path, taken) for path in scope for taken in claimed):
            current.append(index)
            claimed.extend(scope)
            continue
        if current:
            waves.append(current)
        if scope:
            current, claimed = [index], list(scope)
        else:
            waves.append([index])
            current, claimed = [], []
    if current:
        waves.append(current)
    return waves


def _overlaps(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


def derive_sub_context(
    context: ToolContext, subtask: SubTask | None = None, *, root: Path | None = None
) -> ToolContext:
    """Alt ajan bağlamı: görev listesi ve sahip olunan yollar AYRI.

    Alt ajan temiz bir görev listesiyle çalışır — ana ajanın listesini ezmesi
    kullanıcının takip ettiği planı bozardı. `touched` kapanışta parent
    doğrulamasına birleştirilir; kardeşin kanıtı bu ajana yazılmaz. Erişim sınırı aynen taşınır;
    yazma alanı bildirildiyse alt ajan yalnız oraya yazar. `root` verilirse (çalışma
    ağacı izolasyonu) üye o kökte ve KENDİ değişiklik kümesiyle çalışır: ana projenin
    `/undo` kaydına karışmaz, yazma alanı da o köke göre çözülür.
    """
    if root is not None:
        context = ToolContext(
            root=root,
            job_scope=context.job_scope,
            cancelled=context.cancelled,
            restrict_to_root=context.restrict_to_root,
            block_reads_outside_root=context.block_reads_outside_root,
            block_writes_outside_root=context.block_writes_outside_root,
            extra_roots=context.extra_roots,
            chrome=context.chrome,
            hidden_env=context.hidden_env,
            shell_sandbox=context.shell_sandbox,
            sandbox_policy=context.sandbox_policy,
            edit_fuzzy_match=context.edit_fuzzy_match,
            post_edit_syntax_check=context.post_edit_syntax_check,
            shell_fingerprint=context.shell_fingerprint,
            desktop_settings=context.desktop_settings,
        )
    scope: tuple[Path, ...] | None = context.write_scope
    if subtask is not None and subtask.write_scope:
        scope = tuple(writable_path(context, raw).resolve() for raw in subtask.write_scope)
    if subtask is not None and subtask.read_only:
        scope = ()
    return ToolContext(
        root=context.root,
        job_scope=context.job_scope,
        cancelled=context.cancelled,
        changes=context.changes,
        restrict_to_root=context.restrict_to_root,
        # Kök dışı okuma/yazma engeli (P-002) alt ajana da geçer; düşerse üye engeli aşar.
        block_reads_outside_root=context.block_reads_outside_root,
        block_writes_outside_root=context.block_writes_outside_root,
        extra_roots=context.extra_roots,
        chrome=context.chrome,
        hidden_env=context.hidden_env,
        shell_sandbox=context.shell_sandbox,
        sandbox_policy=context.sandbox_policy,
        edit_fuzzy_match=context.edit_fuzzy_match,
        post_edit_syntax_check=context.post_edit_syntax_check,
        shell_fingerprint=context.shell_fingerprint,
        desktop=context.desktop,
        desktop_screenshot_max_width=context.desktop_screenshot_max_width,
        desktop_exclude_fusion_window=context.desktop_exclude_fusion_window,
        desktop_settings=context.desktop_settings,
        write_scope=scope,
        # Tarayıcı ayarları (profil kapısı, varsayılan profil, pencere kipi) devralınır;
        # açık oturum devralınmaz (P-023).
        browser=context.browser.derive(),
    )


def changed_paths(context: ToolContext | None) -> tuple[str, ...]:
    """Model beyanını değil yalnız child executor izini raporla."""
    if context is None:
        return ()
    root = context.root.resolve()
    return tuple(
        sorted(
            str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
            for path in context.touched
        )
    )
