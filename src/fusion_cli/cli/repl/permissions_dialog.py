"""`/permissions` etkileşimli iletişim kutusu — Claude Code'daki sekmeli izin ekranı (#83).

Claude (commands /permissions, permissions#manage-permissions): kurallar Allow / Ask / Deny
sekmelerinde kaynağıyla listelenir, eklenir ve silinir; Workspace sekmesinde çalışma
dizinleri yönetilir; Auto mode sekmesinde son auto mode retleri görülür. Yeni kural
kullanıcı, proje ya da yerel ayar dosyasına kaydedilir.

Kutu yüzeyden bağımsızdır: TUI uygulama-içi modalla (`await_choice`/`await_text`), düz REPL
ok tuşlu seçiciyle (`ui.picker.pick`) sürer. Yazma işi `/permissions add|remove` ve
`/add-dir` ile aynı işlevlerden geçer; ikinci bir yol açılmaz.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ...config import permission_admin
from ...config.permission_rules import PermissionDecision, RuleRow
from ...core.auto_review import ReviewOutcome, ReviewVerdict
from ...core.errors import ConfigError
from ...tools.permission_match import claude_tool_names
from ...ui import messages
from ...ui import permission_dialog_messages as texts
from ...ui.auto_review_view import outcome_line
from ...ui.picker import Choice
from . import auto_mode_command, workspace_commands
from .state import ReplState

#: Sekme değerleri (seçim değeri); kural sekmeleri karar adını taşır.
TAB_WORKSPACE = "workspace"
TAB_AUTO = "auto"
_ADD = "+"
_STATUS = "durum"
#: Kayıt kapsamları: Claude'un üç yazılabilir dosyası.
SCOPE_LOCAL = "local"
SCOPE_PROJECT = "project"
SCOPE_USER = "user"

_TAB_LABELS = {
    PermissionDecision.ALLOW: (texts.TAB_ALLOW, texts.TAB_ALLOW_DESC),
    PermissionDecision.ASK: (texts.TAB_ASK, texts.TAB_ASK_DESC),
    PermissionDecision.DENY: (texts.TAB_DENY, texts.TAB_DENY_DESC),
}


class DialogIO(Protocol):
    """İletişim kutusunun yüzeyden istediği üç işlem."""

    async def choose(self, title: str, choices: Sequence[Choice]) -> str | None: ...

    async def ask(self, prompt: str) -> str | None: ...

    def say(self, text: str) -> None: ...


@dataclass(frozen=True, slots=True)
class CallbackIO:
    """Yüzeyin kendi modal/çıktı işlevlerinden kurulan `DialogIO` (TUI)."""

    choose_fn: Callable[[str, list[Choice]], Awaitable[str | None]]
    ask_fn: Callable[[str], Awaitable[str | None]]
    say_fn: Callable[[str], None]

    async def choose(self, title: str, choices: Sequence[Choice]) -> str | None:
        return await self.choose_fn(title, list(choices))

    async def ask(self, prompt: str) -> str | None:
        return await self.ask_fn(prompt)

    def say(self, text: str) -> None:
        self.say_fn(text)


class PlainIO:
    """Düz REPL: ok tuşlu seçici (`ui.picker.pick`) ve tek satır giriş."""

    def __init__(self, say: Callable[[str], None]) -> None:
        self._say = say

    async def choose(self, title: str, choices: Sequence[Choice]) -> str | None:
        from ...ui.picker import pick

        return pick(choices, title=title)

    async def ask(self, prompt: str) -> str | None:
        try:
            return input(f"{prompt} ")
        except (EOFError, KeyboardInterrupt):
            return None

    def say(self, text: str) -> None:
        self._say(text)


async def run_permissions_dialog(state: ReplState, io: DialogIO) -> str:
    """Sekme seçtir, sekmeyi sür; Esc ile kapanınca kapanış metnini döndür."""
    while True:
        tab = await io.choose(texts.DIALOG_TITLE, tab_choices(state))
        if tab is None:
            return texts.DIALOG_CLOSED
        if tab == TAB_WORKSPACE:
            await _workspace_tab(state, io)
        elif tab == TAB_AUTO:
            await _auto_tab(state, io)
        else:
            await _rules_tab(state, io, PermissionDecision(tab))


def tab_choices(state: ReplState) -> list[Choice]:
    """Beş sekme; kural sekmelerinde kural sayısı, Workspace'te dizin sayısı."""
    rows = permission_admin.rule_rows(state.root)
    tabs = [
        Choice(decision.value, label, f"{desc} · {_count(rows, decision)}")
        for decision, (label, desc) in _TAB_LABELS.items()
    ]
    dirs = 1 + len(state.extra_roots)
    tabs.append(Choice(TAB_WORKSPACE, texts.TAB_WORKSPACE, f"{texts.TAB_WORKSPACE_DESC} · {dirs}"))
    tabs.append(Choice(TAB_AUTO, texts.TAB_AUTO, texts.TAB_AUTO_DESC))
    return tabs


def _count(rows: Sequence[RuleRow], decision: PermissionDecision) -> int:
    return sum(1 for row in rows if row.decision == decision.value)


def _rows(state: ReplState, decision: PermissionDecision) -> list[RuleRow]:
    return [row for row in permission_admin.rule_rows(state.root) if row.decision == decision.value]


async def _rules_tab(state: ReplState, io: DialogIO, decision: PermissionDecision) -> None:
    label = _TAB_LABELS[decision][0]
    while True:
        rows = _rows(state, decision)
        choices = [Choice(_ADD, texts.ADD_RULE, texts.ADD_RULE_DESC)]
        choices.extend(Choice(str(i), row.pattern, row.source) for i, row in enumerate(rows))
        picked = await io.choose(texts.RULES_TITLE.format(tab=label), choices)
        if picked is None:
            return
        if picked == _ADD:
            await _add_rule(state, io, decision)
        else:
            await _rule_actions(state, io, rows[int(picked)])


def scope_choices() -> list[Choice]:
    return [
        Choice(SCOPE_LOCAL, texts.SCOPE_LOCAL, texts.SCOPE_LOCAL_DESC),
        Choice(SCOPE_PROJECT, texts.SCOPE_PROJECT, texts.SCOPE_PROJECT_DESC),
        Choice(SCOPE_USER, texts.SCOPE_USER, texts.SCOPE_USER_DESC),
    ]


async def _add_rule(
    state: ReplState, io: DialogIO, decision: PermissionDecision, suggested: str = ""
) -> None:
    prompt = texts.RULE_PROMPT if not suggested else f"{texts.RULE_PROMPT} [{suggested}]"
    pattern = ((await io.ask(prompt)) or "").strip() or suggested
    if not pattern:
        return
    scope = await io.choose(texts.SCOPE_TITLE, scope_choices())
    if scope is None:
        return
    io.say(add_rule(state, decision, pattern, scope))


def add_rule(state: ReplState, decision: PermissionDecision, pattern: str, scope: str) -> str:
    """Kuralı seçilen Claude dosyasına yaz; `/permissions add` ile aynı metin."""
    try:
        rule = permission_admin.parse_pattern(pattern, decision)
    except ValueError:
        return messages.PERMISSIONS_BAD_PATTERN.format(given=pattern)
    try:
        change = permission_admin.add_permission_rule(
            state.root,
            rule,
            user_level=scope == SCOPE_USER,
            project_shared=scope == SCOPE_PROJECT,
            local_only=scope == SCOPE_LOCAL,
        )
    except ConfigError as error:
        return str(error)
    if not change.changed:
        return messages.PERMISSIONS_EXISTS.format(rule=change.pattern, decision=decision.value)
    return permission_admin.added_message(change, decision)


async def _rule_actions(state: ReplState, io: DialogIO, row: RuleRow) -> None:
    layer = row.source.split(" ", 1)[0]
    if not permission_admin.is_rule_removable(state.root, layer):
        io.say(texts.RULE_READ_ONLY.format(source=row.source))
        return
    choices = [Choice("sil", texts.RULE_DELETE), Choice("geri", texts.RULE_BACK)]
    title = texts.RULE_ACTION_TITLE.format(rule=row.pattern, source=row.source)
    if await io.choose(title, choices) != "sil":
        return
    try:
        removed = permission_admin.remove_permission_rule(state.root, row.rule, path=Path(row.path))
    except ConfigError as error:
        io.say(str(error))
        return
    if removed is None:
        io.say(messages.PERMISSIONS_NOT_FOUND.format(rule=row.pattern, decision=row.decision))
        return
    io.say(
        messages.PERMISSIONS_REMOVED.format(
            rule=removed.pattern, decision=row.decision, path=removed.path
        )
    )


async def _workspace_tab(state: ReplState, io: DialogIO) -> None:
    while True:
        primary = Choice(
            "kok", texts.WORKSPACE_PRIMARY.format(path=state.root), texts.WORKSPACE_PRIMARY_DESC
        )
        extras = [
            Choice(str(i), str(path), texts.WORKSPACE_EXTRA_DESC)
            for i, path in enumerate(state.extra_roots)
        ]
        add = Choice(_ADD, texts.WORKSPACE_ADD, texts.WORKSPACE_ADD_DESC)
        picked = await io.choose(texts.WORKSPACE_TITLE, [add, primary, *extras])
        if picked is None:
            return
        if picked == _ADD:
            path = ((await io.ask(texts.WORKSPACE_PROMPT)) or "").strip()
            if path:
                io.say(workspace_commands.add_dir(state, path))
        elif picked == "kok":
            io.say(texts.WORKSPACE_PRIMARY_FIXED)
        else:
            await _remove_dir(state, io, str(state.extra_roots[int(picked)]))


async def _remove_dir(state: ReplState, io: DialogIO, path: str) -> None:
    choices = [Choice("sil", texts.WORKSPACE_REMOVE), Choice("geri", texts.RULE_BACK)]
    if await io.choose(path, choices) == "sil":
        io.say(workspace_commands.add_dir(state, f"kaldır {path}"))


def recent_denials(state: ReplState) -> list[ReviewOutcome]:
    """Bu oturumda auto mode denetçisinin riskli bulup durdurduğu son çağrılar."""
    snapshot = state.approval_memory.auto_review.snapshot()
    return [item for item in snapshot.recent if item.verdict is ReviewVerdict.RISKY]


def suggested_pattern(outcome: ReviewOutcome) -> str:
    """Reddedilen çağrı için Claude biçiminde kalıp önerisi (kısaltılmış özet kullanılmaz)."""
    primary = claude_tool_names(outcome.tool)[0]
    summary = outcome.summary.strip()
    if primary == "Bash" and summary and not summary.endswith("…"):
        return f"Bash({summary})"
    return primary


async def _auto_tab(state: ReplState, io: DialogIO) -> None:
    while True:
        denials = recent_denials(state)
        choices = [Choice(_STATUS, texts.AUTO_STATUS, texts.AUTO_STATUS_DESC)]
        choices.extend(
            Choice(str(i), outcome_line(item), texts.AUTO_DENIAL_DESC)
            for i, item in enumerate(reversed(denials))
        )
        if not denials:
            io.say(texts.AUTO_NO_DENIALS)
        picked = await io.choose(texts.AUTO_TITLE, choices)
        if picked is None:
            return
        if picked == _STATUS:
            io.say(auto_mode_command.status(state))
            continue
        outcome = list(reversed(denials))[int(picked)]
        suggestion = suggested_pattern(outcome)
        action = Choice(
            "kural",
            texts.AUTO_DENIAL_RULE,
            texts.AUTO_DENIAL_RULE_DESC.format(pattern=suggestion),
        )
        picked = await io.choose(outcome_line(outcome), [action, Choice("geri", texts.RULE_BACK)])
        if picked == "kural":
            await _add_rule(state, io, PermissionDecision.ALLOW, suggestion)
