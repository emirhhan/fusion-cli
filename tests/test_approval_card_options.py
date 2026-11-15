"""Onay kartı seçenekleri Claude gibi (#82): kabukta yalnız kalıcı seçenek."""

from __future__ import annotations

from fusion_cli.appserver.bridges import _approval_options
from fusion_cli.engines.agent.approval import ApprovalRequest


class _Kabuk:
    name = "run_shell"


class _Web:
    name = "web_fetch"


def _degerler(request: ApprovalRequest) -> list[str]:
    return [item["deger"] for item in _approval_options(request)]


def test_masaustu_kabuk_kartinda_oturum_secenegi_yok():
    request = ApprovalRequest(tool=_Kabuk(), args={"command": "npm test"}, danger=None)
    assert request.can_remember and request.can_persist
    assert request.offers_session is False
    assert _degerler(request) == ["once", "always", "deny"]


def test_kalici_kural_yazilamayan_kabukta_oturum_secenegi_kalir():
    request = ApprovalRequest(
        tool=_Kabuk(), args={"command": "npm test"}, danger=None, pre_ask=None, effect=None
    )
    from dataclasses import replace

    from fusion_cli.core.tools import ToolEffect

    uzak = replace(request, effect=ToolEffect.REMOTE_WRITE)
    assert uzak.can_persist is False
    assert uzak.offers_session is uzak.can_remember


def test_kabuk_disi_kartta_oturum_secenegi_var():
    request = ApprovalRequest(tool=_Web(), args={"url": "https://example.com"}, danger=None)
    assert "session" in _degerler(request)
