"""Mobil sohbetin yerel marka fontu çevrimdışı paketlenebilir biçimde sunulur."""

import asyncio
from pathlib import Path

from .test_remote_service import Rig

_FONT = Path(__file__).resolve().parents[1] / "app/src/brand/fonts/InterVariable.woff2"


async def test_pwa_font_and_license_are_served_locally(tmp_path):
    rig = Rig(tmp_path)
    try:
        font = await rig.client.get("/InterVariable.woff2")
        license_text = await rig.client.get("/Inter-LICENSE.txt")
        assert font.status_code == 200
        assert font.headers["content-type"] == "font/woff2"
        assert font.content == await asyncio.to_thread(_FONT.read_bytes)
        assert font.content.startswith(b"wOF2")
        assert license_text.status_code == 200
        assert "Inter Project Authors" in license_text.text
    finally:
        await rig.client.aclose()
