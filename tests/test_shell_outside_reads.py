"""Salt okunur kabuk komutunun çalışma dizinleri dışını okuması Claude gibi sorulur (#56)."""

from __future__ import annotations

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.approval import (
    ApprovalMemory,
    ApprovalMode,
    Decision,
    build_policy,
    resolve_request,
)
from fusion_cli.tools import build_registry
from fusion_cli.tools.shell_outside_reads import shell_outside_read_target

from .fakes import AlwaysReject

_REG = build_registry()


@pytest.fixture
def alan(tmp_path):
    kok = tmp_path / "proje"
    kok.mkdir()
    (kok / "a.txt").write_text("x")
    disari = tmp_path / "disari"
    disari.mkdir()
    (disari / "b.txt").write_text("y")
    return kok, disari


def test_hedef_tespiti(alan):
    kok, disari = alan
    assert shell_outside_read_target("cat a.txt", kok) is None
    assert shell_outside_read_target(f"cat {kok}/a.txt", kok) is None
    assert shell_outside_read_target(f"cat {disari}/b.txt", kok) is not None
    assert shell_outside_read_target("head ../disari/b.txt", kok) is not None
    assert shell_outside_read_target(f"ls {disari}", kok, (disari,)) is None
    # Salt okunur olmayan komut bu denetimin konusu değil (kip zaten sorar).
    assert shell_outside_read_target(f"rm {disari}/b.txt", kok) is None


async def _karar(mod, komut, kok):
    ctx = ToolContext(root=kok)
    istek = await resolve_request(_REG.get("run_shell"), {"command": komut}, root=kok, context=ctx)
    return await build_policy(mod, AlwaysReject(), ApprovalMemory()).decide(istek)


@pytest.mark.parametrize(
    ("mod", "beklenen"),
    [
        (ApprovalMode.SECURITY, Decision.DENIED),
        (ApprovalMode.ACCEPT_EDITS, Decision.DENIED),
        (ApprovalMode.PLAN, Decision.DENIED),
        (ApprovalMode.DONT_ASK, Decision.BLOCKED),
        (ApprovalMode.AUTO, Decision.ALLOW),
        (ApprovalMode.BYPASS, Decision.ALLOW),
    ],
)
async def test_disari_okuyan_kabuk_komutu_kipe_gore(alan, mod, beklenen):
    kok, disari = alan
    assert await _karar(mod, f"cat {disari}/b.txt", kok) is beklenen


@pytest.mark.parametrize(
    "mod", [ApprovalMode.SECURITY, ApprovalMode.ACCEPT_EDITS, ApprovalMode.PLAN, ApprovalMode.DONT_ASK]
)
async def test_icerideki_okuma_sorulmaz(alan, mod):
    kok, _ = alan
    assert await _karar(mod, "cat a.txt", kok) is Decision.ALLOW
