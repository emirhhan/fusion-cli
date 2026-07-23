"""Onay politikaları — üç modun davranışı."""

from __future__ import annotations

import pytest

from fusion_cli.core.tools import Tool
from fusion_cli.engines.agent.approval import (
    ApprovalMode,
    Decision,
    build_policy,
    build_request,
)

from .fakes import AlwaysApprove, AlwaysReject


def _arac(ad="write_file", *, mutating=True):
    return Tool(name=ad, description="", parameters={}, run=lambda a, c: None, mutating=mutating)


@pytest.mark.parametrize(
    ("mod", "beklenen"),
    [(ApprovalMode.AUTO, Decision.ALLOW), (ApprovalMode.PLAN, Decision.BLOCKED)],
)
async def test_zararsiz_degisiklik_modlara_gore_karara_baglanir(mod, beklenen):
    politika = build_policy(mod, AlwaysApprove())

    karar = await politika.decide(build_request(_arac(), {"path": "a.txt"}))

    assert karar is beklenen


async def test_auto_modda_yikici_komut_yine_de_sorulur():
    politika = build_policy(ApprovalMode.AUTO, AlwaysReject())

    karar = await politika.decide(build_request(_arac("run_shell"), {"command": "rm -rf build"}))

    assert karar is Decision.DENIED


async def test_auto_modda_yikici_olmayan_komut_sorulmaz():
    politika = build_policy(ApprovalMode.AUTO, AlwaysReject())

    karar = await politika.decide(build_request(_arac("run_shell"), {"command": "pytest -q"}))

    assert karar is Decision.ALLOW


async def test_security_modda_her_degisiklik_sorulur():
    politika = build_policy(ApprovalMode.SECURITY, AlwaysReject())

    karar = await politika.decide(build_request(_arac(), {"path": "a.txt"}))

    assert karar is Decision.DENIED


async def test_security_modda_onay_verilirse_gecer():
    politika = build_policy(ApprovalMode.SECURITY, AlwaysApprove())

    assert await politika.decide(build_request(_arac(), {})) is Decision.ALLOW


async def test_plan_modu_kullaniciya_hic_sormaz():
    class _Patlayan:
        async def confirm(self, request):
            raise AssertionError("plan modunda soru sorulmamalı")

    politika = build_policy(ApprovalMode.PLAN, _Patlayan())

    assert await politika.decide(build_request(_arac(), {})) is Decision.BLOCKED


def test_tehlike_gerekcesi_isteğe_islenir():
    istek = build_request(_arac("run_shell"), {"command": "git push --force"})

    assert istek.danger == "uzak geçmişi ezen force push"


def test_zararsiz_istekte_tehlike_yok():
    assert build_request(_arac("run_shell"), {"command": "ls"}).danger is None
