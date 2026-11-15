"""MCP elicitation Claude Code gibi: form ve url kipleri (#257).

Belge: code.claude.com/docs/en/mcp, "Respond to MCP elicitation requests".
"""

from __future__ import annotations

import pytest
from mcp import types

from fusion_cli.mcp_bridge import elicitation
from fusion_cli.mcp_bridge.elicitation import (
    ACCEPT,
    DECLINE,
    OPEN,
    elicitation_callback,
    register_elicitation_asker,
)


class _Sorucu:
    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.questions: list[str] = []

    async def ask(self, question, options=(), recommended=None) -> str:
        self.questions.append(question)
        return self.answers.pop(0)


@pytest.fixture(autouse=True)
def _temiz():
    yield
    register_elicitation_asker(None)


def _form() -> types.ElicitRequestFormParams:
    return types.ElicitRequestFormParams(
        message="Giriş bilgisi",
        requestedSchema={
            "type": "object",
            "properties": {
                "kullanici": {"type": "string", "title": "Kullanıcı adı"},
                "adet": {"type": "integer"},
                "onay": {"type": "boolean"},
            },
            "required": ["kullanici"],
        },
    )


async def test_form_alanlari_sorulur_turlerine_cevrilir():
    sorucu = _Sorucu(ACCEPT, "emir", "3", "evet")
    register_elicitation_asker(sorucu)

    result = await elicitation_callback("crm")(None, _form())

    assert result.action == "accept"
    assert result.content == {"kullanici": "emir", "adet": 3, "onay": True}
    assert "crm" in sorucu.questions[0] and "Kullanıcı adı" in sorucu.questions[1]


async def test_form_reddi_ve_zorunlu_bos_iptal():
    register_elicitation_asker(_Sorucu(DECLINE))
    declined = await elicitation_callback("crm")(None, _form())
    register_elicitation_asker(_Sorucu(ACCEPT, ""))
    cancelled = await elicitation_callback("crm")(None, _form())

    assert declined.action == "decline" and cancelled.action == "cancel"


async def test_soru_sorabilen_taraf_yoksa_iptal():
    result = await elicitation_callback("crm")(None, _form())

    assert result.action == "cancel"


async def test_url_kipi_tarayicida_acar_uzun_url_yalniz_red(monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(elicitation.webbrowser, "open", opened.append)
    register_elicitation_asker(_Sorucu(OPEN))
    params = types.ElicitRequestURLParams(
        message="Oturum aç", url="https://giris.example.com/a", elicitationId="e1"
    )

    accepted = await elicitation_callback("crm")(None, params)
    register_elicitation_asker(_Sorucu(DECLINE))
    long_url = types.ElicitRequestURLParams(
        message="x", url="https://e.example.com/?" + "%41" * 3_000, elicitationId="e2"
    )
    refused = await elicitation_callback("crm")(None, long_url)

    assert accepted.action == "accept" and opened == ["https://giris.example.com/a"]
    assert refused.action == "decline"


def test_istemci_form_ve_url_bildirir():
    from mcp import ClientSession

    session = ClientSession(None, None, elicitation_callback=elicitation_callback("x"))  # type: ignore[arg-type]

    assert session._elicitation_callback is not None
