"""Uzak izinlerin hesap, eylem ve hedef dışına taşmama sözleşmesi."""

from __future__ import annotations

import pytest

from fusion_cli.core.tools import Tool, ToolArgs, ToolContext, ToolEffect, ToolResult
from fusion_cli.engines.agent.approval import (
    ApprovalAnswer,
    ApprovalMemory,
    ApprovalMode,
    ApprovalRequest,
    Decision,
    build_policy,
    build_request,
)


def _offline_executor(args: ToolArgs, context: ToolContext) -> ToolResult:
    raise AssertionError("Onay sözleşmesi araç yürütmemeli")


class _SessionThenDeny:
    """İlk kapsamı onaylar; sonraki kapsam için kullanıcı reddini temsil eder."""

    def __init__(self) -> None:
        self.requests: list[ApprovalRequest] = []

    async def confirm(self, request: ApprovalRequest) -> ApprovalAnswer:
        self.requests.append(request)
        return ApprovalAnswer.SESSION if len(self.requests) == 1 else ApprovalAnswer.DENY


@pytest.mark.parametrize(
    "changed_args",
    [
        {"account": "hesap-b", "action": "update", "target": "kaynak-a"},
        {"account": "hesap-a", "action": "publish", "target": "kaynak-a"},
        {"account": "hesap-a", "action": "update", "target": "kaynak-b"},
    ],
    ids=["hesap-degisimi", "eylem-degisimi", "hedef-degisimi"],
)
async def test_remote_session_permission_does_not_authorize_changed_scope(
    changed_args: dict[str, object],
) -> None:
    """A kapsamı için alınan izin B kapsamının açık reddini atlamamalı."""
    remote_tool = Tool(
        name="offline_server__resource_update",
        description="Çevrimdışı uzak kapsam örneği",
        parameters={},
        run=_offline_executor,
        mutating=True,
        effect=ToolEffect.REMOTE_WRITE,
    )
    prompter = _SessionThenDeny()
    memory = ApprovalMemory()
    first_policy = build_policy(ApprovalMode.SECURITY, prompter, memory)
    first_request = build_request(
        remote_tool, {"account": "hesap-a", "action": "update", "target": "kaynak-a"}
    )
    assert await first_policy.decide(first_request) is Decision.ALLOW

    next_policy = build_policy(ApprovalMode.SECURITY, prompter, memory)
    assert await next_policy.decide(build_request(remote_tool, changed_args)) is Decision.DENIED
    assert len(prompter.requests) == 2


def test_shell_alias_permission_remains_exact_command_only() -> None:
    """Uzak kapsam düzeltmesi mevcut dar shell alias kapsamını genişletmemeli."""
    memory = ApprovalMemory()
    alias = Tool("bash", "", {}, _offline_executor, mutating=True)
    canonical = Tool("run_shell", "", {}, _offline_executor, mutating=True)
    memory.remember(build_request(alias, {"command": "git status"}))
    assert memory.is_remembered(build_request(canonical, {"command": "git status"}))
    assert not memory.is_remembered(build_request(canonical, {"command": "git diff"}))


def test_verified_scope_reuses_only_same_target_and_can_be_revoked() -> None:
    """Adaptör kapsamı yeniden kullanılabilir; hesap değişimi ve iptal bunu kapatır."""
    from fusion_cli.core.tools import AuthorizationScope

    def scope(args: ToolArgs) -> AuthorizationScope:
        return AuthorizationScope("offline", str(args["account"]), "update", (str(args["target"]),))

    tool = Tool(
        "remote",
        "",
        {},
        _offline_executor,
        mutating=True,
        effect=ToolEffect.REMOTE_WRITE,
        scope_resolver=scope,
    )
    memory = ApprovalMemory()
    first = build_request(tool, {"account": "a", "target": "one"})
    memory.remember(first)
    assert memory.is_remembered(build_request(tool, {"account": "a", "target": "one"}))
    assert not memory.is_remembered(build_request(tool, {"account": "b", "target": "one"}))
    assert not memory.is_remembered(build_request(tool, {"account": "a", "target": "two"}))
    memory.revoke()
    assert not memory.is_remembered(first)


async def test_revocation_while_waiting_cannot_restore_session_permission() -> None:
    """Bekleyen eski karar, iptal edilmiş oturum iznini geri getiremez."""
    memory = ApprovalMemory()
    tool = Tool("write_file", "", {}, _offline_executor, mutating=True)
    request = build_request(tool, {"path": "offline.txt"})

    class RevokingPrompter:
        async def confirm(self, request: ApprovalRequest) -> ApprovalAnswer:
            memory.revoke()
            return ApprovalAnswer.SESSION

    policy = build_policy(ApprovalMode.SECURITY, RevokingPrompter(), memory)
    assert await policy.decide(request) is Decision.BLOCKED
    assert not memory.is_remembered(request)
