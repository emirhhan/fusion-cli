"""Masaüstü hedefi headless (stream-json) ve uzak onay görünümünde de taşınır (P-007 inceleme)."""

from __future__ import annotations

import asyncio
import io
import json

from fusion_cli.cli.headless import JsonLinesPrompter
from fusion_cli.core.desktop_settings import DesktopLevel, DesktopTarget
from fusion_cli.core.tools import Tool
from fusion_cli.engines.agent.approval import ApprovalRequest
from fusion_cli.remote.rpc import RemoteService

_MAIL = DesktopTarget("Mail", "com.apple.mail", 41, DesktopLevel.CLICK, "uyarı", "Button 'Sil'")
_PAYLOAD = {
    "uygulama": "Mail",
    "paket": "com.apple.mail",
    "kademe": "click",
    "kademe_etiket": "tıkla",
    "uyari": "uyarı",
    "oge": "Button 'Sil'",
}


def test_hedef_tek_bicimde_serilestirilir():
    assert _MAIL.payload() == _PAYLOAD


def test_headless_onay_istegi_masaustu_hedefini_tasir():
    """Ölçüldü (31 Ekim): `ApprovalRequested` satırında hedef uygulama/kademe yoktu."""
    tool = Tool(name="desktop_click", description="", parameters={}, run=None, mutating=True)  # type: ignore[arg-type]
    request = ApprovalRequest(tool=tool, args={"x": 1}, danger=None, desktop_target=_MAIL)
    out = io.StringIO()
    prompter = JsonLinesPrompter(
        stdin=io.StringIO('{"istek_id": "1", "karar": "reddet"}\n'), stdout=out
    )

    asyncio.run(prompter.confirm(request))

    first = json.loads(out.getvalue().splitlines()[0])
    assert first["masaustu"] == _PAYLOAD


def test_uzak_onay_gorunumu_masaustu_hedefini_tasir():
    view = RemoteService._question_view(
        "q1", {"tur": "onay", "arac": "desktop_click", "masaustu": _PAYLOAD}
    )
    assert view["desktop"] == _PAYLOAD and view["stepUp"] is True
