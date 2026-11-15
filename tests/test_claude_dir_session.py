"""`.claude/` yazımı için oturumluk seçenek — Claude gibi (#82).

Claude (permission-modes#protected-paths): korumalı `.claude` yazımında kart "Yes, and allow
Claude to edit files in this project's .claude folder for this session" sunar; `~/.claude/`
için ayrı bir sürümü vardır. Allow kuralı korumalı yazımı açmaz; oturum izni açar.
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.appserver.bridges import _approval_options
from fusion_cli.core.tools import Tool
from fusion_cli.engines.agent.approval import (
    ApprovalAnswer,
    ApprovalMemory,
    ApprovalMode,
    Decision,
    build_policy,
    build_request,
)
from fusion_cli.ui import messages


def _yazici() -> Tool:
    return Tool(
        name="write_file", description="", parameters={}, run=lambda a, c: None, mutating=True
    )


class _Soran:
    def __init__(self, cevap: object) -> None:
        self.cevap = cevap
        self.soruldu: list[object] = []

    async def confirm(self, request):
        self.soruldu.append(request)
        return self.cevap


def test_proje_claude_klasoru_oturum_secenegi_sunar(tmp_path):
    istek = build_request(_yazici(), {"path": ".claude/agents/x.md", "content": ""}, root=tmp_path)
    assert istek.protected is not None
    assert istek.offers_session and istek.can_remember and not istek.can_persist
    secenek = {s["deger"]: s for s in _approval_options(istek, tmp_path)}["session"]
    assert secenek["etiket"] == messages.CLAUDE_DIR_SESSION_PROJECT


def test_ev_claude_klasoru_ayri_secenek(tmp_path):
    hedef = Path.home() / ".claude" / "settings.json"
    istek = build_request(_yazici(), {"path": str(hedef), "content": "{}"}, root=tmp_path)
    secenek = {s["deger"]: s for s in _approval_options(istek, tmp_path)}["session"]
    assert secenek["etiket"] == messages.CLAUDE_DIR_SESSION_USER


def test_git_klasoru_oturum_secenegi_sunmaz(tmp_path):
    istek = build_request(_yazici(), {"path": ".git/config", "content": ""}, root=tmp_path)
    assert istek.protected is not None
    assert not istek.offers_session
    assert "session" not in {s["deger"] for s in _approval_options(istek, tmp_path)}


def test_kabuk_ile_claude_yazimi_oturum_secenegi_sunmaz(tmp_path):
    kabuk = Tool(
        name="run_shell", description="", parameters={}, run=lambda a, c: None, mutating=True
    )
    istek = build_request(kabuk, {"command": "touch .claude/x"}, root=tmp_path)
    assert istek.protected is not None and not istek.offers_session


async def test_oturum_izni_sonraki_claude_yazimini_sormaz(tmp_path):
    bellek = ApprovalMemory()
    soran = _Soran(ApprovalAnswer.SESSION)
    politika = build_policy(ApprovalMode.SECURITY, soran, bellek)
    ilk = build_request(_yazici(), {"path": ".claude/agents/a.md", "content": ""}, root=tmp_path)
    assert await politika.decide(ilk) is Decision.ALLOW
    ikinci = build_request(
        _yazici(), {"path": ".claude/commands/b.md", "content": ""}, root=tmp_path
    )
    assert await politika.decide(ikinci) is Decision.ALLOW
    assert len(soran.soruldu) == 1
    # İzin yalnız projenin .claude klasörü içindir: .git yine sorulur.
    git = build_request(_yazici(), {"path": ".git/config", "content": ""}, root=tmp_path)
    await politika.decide(git)
    assert len(soran.soruldu) == 2
