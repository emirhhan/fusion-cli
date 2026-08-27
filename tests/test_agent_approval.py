"""Onay politikaları — üç modun davranışı."""

from __future__ import annotations

import pytest

from fusion_cli.core.tools import Tool
from fusion_cli.engines.agent.approval import (
    ApprovalAnswer,
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


async def test_oturum_izni_ayni_araci_tekrar_sormaz():
    class _OturumOnayi:
        def __init__(self):
            self.calls = 0

        async def confirm(self, request):
            self.calls += 1
            return ApprovalAnswer.SESSION

    prompter = _OturumOnayi()
    politika = build_policy(ApprovalMode.SECURITY, prompter)
    request = build_request(_arac(), {"path": "a.txt"})

    assert await politika.decide(request) is Decision.ALLOW
    assert await politika.decide(request) is Decision.ALLOW
    assert prompter.calls == 1


async def test_yikici_istekte_oturum_izni_bir_defalik_sayilir():
    class _OturumOnayi:
        def __init__(self):
            self.calls = 0

        async def confirm(self, request):
            self.calls += 1
            return ApprovalAnswer.SESSION

    prompter = _OturumOnayi()
    politika = build_policy(ApprovalMode.AUTO, prompter)
    request = build_request(_arac("run_shell"), {"command": "rm -rf build"})

    assert await politika.decide(request) is Decision.ALLOW
    assert await politika.decide(request) is Decision.ALLOW
    assert prompter.calls == 2


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


# --- Gözetimsiz kabuk: beyaz liste ------------------------------------------ #


async def test_auto_kipte_taninmayan_kabuk_komutu_sorar():
    """Kara listeye takılmayan her komutun sessizce çalışması asıl açıktı.

    `node -e "...rmSync..."` hiçbir tehlike kalıbına uymaz; eskiden auto kipte
    hiç sorulmadan çalışırdı.
    """
    from fusion_cli.engines.agent.approval import AutoApproval, build_request
    from fusion_cli.tools.shell import run_shell

    arac = Tool(
        name="run_shell",
        description="",
        parameters={},
        run=run_shell,
        mutating=True,
    )
    args = {"command": "node -e \"require('fs').rmSync('/x')\""}
    prompter = _SahtePrompter(cevap=False)

    karar = await AutoApproval(prompter).decide(build_request(arac, args))

    assert prompter.soruldu, "tanınmayan komut onaya sunulmalı"
    assert karar is Decision.DENIED


async def test_auto_kipte_salt_okunur_komut_sorulmaz():
    """Her `ls` için onay istemek kullanıcıyı yorar ve onayı anlamsızlaştırır."""
    from fusion_cli.engines.agent.approval import AutoApproval, build_request
    from fusion_cli.tools.shell import run_shell

    arac = Tool(
        name="run_shell",
        description="",
        parameters={},
        run=run_shell,
        mutating=True,
    )
    prompter = _SahtePrompter(cevap=True)

    karar = await AutoApproval(prompter).decide(build_request(arac, {"command": "git status"}))

    assert not prompter.soruldu
    assert karar is Decision.ALLOW


class _SahtePrompter:
    def __init__(self, cevap: bool) -> None:
        self.cevap = cevap
        self.soruldu = False

    async def confirm(self, request) -> bool:
        self.soruldu = True
        return self.cevap
