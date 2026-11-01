"""Çalışma dizinleri dışından okuma Claude Code ile birebir (#56).

Kaynak: https://code.claude.com/docs/en/permissions#permission-system (Read-only satırı).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.core.artifacts import ArtifactStore
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.approval import (
    ApprovalMemory,
    ApprovalMode,
    Decision,
    build_policy,
    resolve_request,
)
from fusion_cli.tools import build_registry
from fusion_cli.tools.outside_reads import reads_outside

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


async def _karar(mod, args, context):
    istek = await resolve_request(_REG.get("read_file"), args, root=context.root, context=context)
    return await build_policy(mod, AlwaysReject(), ApprovalMemory()).decide(istek)


def test_kapi_yalniz_disari_okumada_acilir(alan):
    kok, disari = alan
    ctx = ToolContext(root=kok)
    assert not reads_outside("read_file", {"path": "a.txt"}, ctx)
    assert not reads_outside("list_dir", {}, ctx)
    assert reads_outside("read_file", {"path": str(disari / "b.txt")}, ctx)
    assert reads_outside("grep_search", {"path": "../disari"}, ctx)
    assert not reads_outside("read_file", {"path": str(disari / "b.txt")}, ToolContext(
        root=kok, extra_roots=(disari,)
    ))  # fmt: skip


def test_cikti_deposu_icerideki_sayilir(alan, tmp_path):
    kok, _ = alan
    depo = tmp_path / "depo"
    depo.mkdir()
    ctx = ToolContext(root=kok, artifacts=ArtifactStore(depo))
    assert not reads_outside("read_file", {"path": str(depo / "x.txt")}, ctx)


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
async def test_disari_okuma_kiplere_gore(alan, mod, beklenen):
    kok, disari = alan
    ctx = ToolContext(root=kok)
    assert await _karar(mod, {"path": str(disari / "b.txt")}, ctx) is beklenen


async def test_kok_disi_okuma_kapaliyken_sorulmadan_engellenir(alan):
    kok, disari = alan
    ctx = ToolContext(root=kok, block_reads_outside_root=True)
    assert await _karar(ApprovalMode.BYPASS, {"path": str(disari / "b.txt")}, ctx) is (
        Decision.BLOCKED
    )


async def test_oturum_izni_dizine_baglanir(alan):
    kok, disari = alan
    istek = await resolve_request(
        _REG.get("read_file"), {"path": str(disari / "b.txt")}, root=kok,
        context=ToolContext(root=kok),
    )  # fmt: skip
    assert istek.outside_dir == str(Path(disari).resolve())
