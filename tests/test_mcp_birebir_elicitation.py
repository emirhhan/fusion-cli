"""MCP elicitation Claude Code gibi: form ve url kipleri (#257).

Belge: code.claude.com/docs/en/mcp, "Respond to MCP elicitation requests".
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from contextvars import Context
from types import SimpleNamespace

import pytest
from mcp import types

from fusion_cli.config.models import McpServerConfig
from fusion_cli.mcp_bridge import client as mcp_client
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


@pytest.fixture
def eliciting_client(monkeypatch):
    entered = {}
    proceed = {}

    @asynccontextmanager
    async def transport(*args, **kwargs):
        yield None, None

    class Session:
        def __init__(self, *args, elicitation_callback, **kwargs):
            self.elicitation = elicitation_callback

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            pass

        async def initialize(self):
            return SimpleNamespace(instructions="")

        async def call_tool(self, name, args, **kwargs):
            entered[name].set()
            await proceed[name].wait()
            result = await asyncio.create_task(self.elicitation(None, _form()), context=Context())
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=result.action)]
            )

    monkeypatch.setattr(mcp_client, "open_mcp_stream", transport)
    monkeypatch.setattr(mcp_client, "ClientSession", Session)

    async def start(client, name, asker):
        entered[name] = asyncio.Event()
        proceed[name] = asyncio.Event()

        async def call():
            register_elicitation_asker(asker)
            return await client.call("crm", name, {})

        task = asyncio.create_task(call())
        await asyncio.wait_for(entered[name].wait(), 1)
        return task

    return start, proceed


async def test_overlapping_clients_with_same_server_name_keep_turn_askers(eliciting_client):
    start, proceed = eliciting_client
    config = (McpServerConfig("crm"),)
    asker = _Sorucu(ACCEPT, "owner", "3", "evet")
    async with mcp_client.McpClient(config) as quiet, mcp_client.McpClient(config) as interactive:
        quiet_task = await start(quiet, "quiet", None)
        interactive_task = await start(interactive, "interactive", asker)
        proceed["quiet"].set()
        assert (await quiet_task).output == "cancel"
        proceed["interactive"].set()
        assert (await interactive_task).output == "accept"

    assert len(asker.questions) == 4


async def test_shared_client_cancels_ambiguous_overlap_and_can_prompt_on_later_call(
    eliciting_client,
):
    start, proceed = eliciting_client
    config = (McpServerConfig("crm"),)
    asker = _Sorucu(ACCEPT, "owner", "3", "evet")
    async with mcp_client.McpClient(config) as client:
        quiet = await start(client, "quiet", None)
        interactive = await start(client, "interactive", asker)
        proceed["quiet"].set()
        assert (await quiet).output == "cancel"
        proceed["interactive"].set()
        assert (await interactive).output == "cancel"
        assert not asker.questions

        later = await start(client, "later", asker)
        proceed["later"].set()
        assert (await later).output == "accept"

    assert len(asker.questions) == 4
