"""`fusion agent` başlangıç kipi (#328, #353).

Claude: `claude -p` kip verilmeden Manual başlar ve onay gerektiren çağrıyı sorulmadan
reddeder (allow kuralı/kanca onaylamadıkça); bayrak adı `--permission-mode`.
"""

from __future__ import annotations

from fusion_cli.cli import app as cli_app
from fusion_cli.cli.unprompted import UnpromptedPrompter
from fusion_cli.core.tools import Tool
from fusion_cli.engines.agent.approval import (
    ApprovalAnswer,
    ApprovalMode,
    Decision,
    build_policy,
    build_request,
)


def _secenekler(mode: str, kanal: str | None = None):
    return cli_app._headless_options(
        "görev",
        mode=mode,
        as_json=False,
        output_format="text",
        json_schema=None,
        agent_name=None,
        permission_channel=kanal,
        append_system_prompt=None,
        allowed_tools=None,
        disallowed_tools=None,
    )


def test_varsayilan_kip_manual_ve_sorulmadan_reddeder():
    secenek = _secenekler(cli_app.HEADLESS_DEFAULT_MODE)
    assert secenek.approval is ApprovalMode.SECURITY and secenek.deny_unprompted


def test_acik_kip_verilince_eski_davranis():
    secenek = _secenekler("auto")
    assert secenek.approval is ApprovalMode.AUTO and not secenek.deny_unprompted


def test_izin_kanali_varsa_sorulur():
    assert not _secenekler(cli_app.HEADLESS_DEFAULT_MODE, "stdin").deny_unprompted


async def test_sormayan_onaylayici_degisikligi_reddeder(tmp_path):
    arac = Tool(
        name="write_file", description="", parameters={}, run=lambda a, c: None, mutating=True
    )
    politika = build_policy(ApprovalMode.SECURITY, UnpromptedPrompter())
    karar = await politika.decide(build_request(arac, {"path": "a.txt"}, root=tmp_path))
    assert karar is not Decision.ALLOW
    assert await UnpromptedPrompter().confirm(build_request(arac, {})) is ApprovalAnswer.UNAVAILABLE


def test_permission_mode_bayragi_tanimli():
    from typer.testing import CliRunner

    yardim = CliRunner().invoke(cli_app.app, ["agent", "--help"]).output
    assert "--permission-mode" in yardim
