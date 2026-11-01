"""Bütünlük sınıfı gerçek turda ayrı kurtarma üretir.

Sınıflandırma tek başına işe yaramaz: kapanmamış blokta sözleşme hatırlatılmalı,
kesilmiş yanıtta "kaldığın yerden devam et" denmeli. İkisini aynı nota bağlamak,
yapılan işi çöpe atıyor ya da modele yanlış şeyi düzelttiriyordu.
"""

from __future__ import annotations

import pytest

from fusion_cli.core.web_response import ResponseIntegrity
from fusion_cli.engines.agent.reflexion import integrity_note


def test_kesilmis_yanit_devam_notu_alir():
    not_ = integrity_note(ResponseIntegrity.TRUNCATED)

    assert not_ is not None
    assert "devam" in not_.content.casefold()


def test_kapanmamis_blok_sozlesme_notu_alir():
    not_ = integrity_note(ResponseIntegrity.UNCLOSED_BLOCK)

    assert not_ is not None
    icerik = not_.content.casefold()
    assert "bloğu" in icerik
    assert "tam olarak" in icerik or "kapat" in icerik


def test_bos_yanit_sadelestirme_notu_alir():
    not_ = integrity_note(ResponseIntegrity.EMPTY)

    assert not_ is not None
    assert "tek" in not_.content.casefold() or "kısa" in not_.content.casefold()


def test_saglam_yanit_not_almaz():
    assert integrity_note(ResponseIntegrity.OK) is None


@pytest.mark.parametrize("is_capture", [False, True])
async def test_browser_fallback_provenance_belongs_to_returned_response(monkeypatch, is_capture):
    from dataclasses import replace

    from fusion_cli.core.types import Message
    from fusion_cli.providers import web_browser
    from fusion_cli.providers.web_response import ObservedResponse
    from fusion_cli.providers.web_session import WebTurnContext

    from .test_web_conversation import _RET, _session
    from .test_web_tool_provenance import observed_origin

    origin = observed_origin()
    messages = (Message("user", "ilk"), Message("user", "sonraki"))

    manager = _fallback_manager(messages)

    async def ready(*args, **kwargs):
        return None

    async def choice(*args, **kwargs):
        return "Pro"

    async def adjacent(*args, **kwargs):
        return "Flash"

    async def tier(*args, **kwargs):
        return ""

    answers = iter([(_RET, "rejected-node"), ("accepted", "accepted-node")])

    async def send(*args, **kwargs):
        text, identity = next(answers)
        kwargs["observation_sink"](
            ObservedResponse(text, replace(origin, observed_container_id=identity))
        )
        return text

    monkeypatch.setattr(web_browser, "_open_past_human_verification", ready)
    monkeypatch.setattr(web_browser, "_apply_model_choice", choice)
    monkeypatch.setattr(web_browser, "switch_to_adjacent_model", adjacent)
    monkeypatch.setattr(web_browser, "observed_tier", tier)
    monkeypatch.setattr(web_browser, "_send_turn", send)
    result = await web_browser._deliver_turn(
        manager,
        _session(),
        web_browser.WEB_BROWSER_PROVIDERS["chatgpt_web"],
        None,
        messages,
        turn=WebTurnContext(web_call_context=origin.call_context, is_capture_probe=is_capture),
    )
    assert result.text == (_RET if is_capture else "accepted")
    assert result.provenance.observed_container_id == (
        "rejected-node" if is_capture else "accepted-node"
    )
    assert result.provenance.observed_model is None


def _fallback_manager(messages):
    from fusion_cli.providers import web_browser

    class Page:
        def is_closed(self):
            return False

    state = web_browser.ConversationState(
        Page(), sent_count=1, prefix_digest=web_browser.conversation_digest(messages[:1])
    )

    class Manager:
        def conversation(self, *args):
            return state

        def confirm_fallback(self, *args):
            pass

        def remember_conversation(self, *args):
            pass

        async def flush_closed(self):
            pass

        def take_mode_note(self, *args):
            return ""

    return Manager()
