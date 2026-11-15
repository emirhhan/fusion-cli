"""Chrome dosya yükleme: hard link, kimlik bilgisi adı ve okuma engeli (#437)."""

from __future__ import annotations

import os

import pytest

from fusion_cli.core.sandbox_policy import SandboxPolicy
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import chrome


class _Kopru:
    def __init__(self) -> None:
        self.cagrilar: list[str] = []

    async def invoke(self, name, data):
        self.cagrilar.append(name)
        return {"ok": True, "veri": {"count": len(data.get("files", []))}}


async def _yukle(context: ToolContext, value: str):
    return await chrome.chrome_action({"action": "upload", "ref": "e1", "value": value}, context)


@pytest.mark.parametrize(
    "yol", [".env", ".env.local", "sunucu.pem", "ozel.key", ".ssh/config", ".aws/credentials"]
)
async def test_kimlik_bilgisi_dosyasi_yuklenmez(tmp_path, yol):
    hedef = tmp_path / yol
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text("gizli", encoding="utf-8")
    kopru = _Kopru()
    sonuc = await _yukle(ToolContext(root=tmp_path, chrome=kopru), yol)
    assert not sonuc.ok and "kimlik bilgisi" in sonuc.output and kopru.cagrilar == []


async def test_hard_link_yuklenmez(tmp_path):
    asil = tmp_path / "asil.txt"
    asil.write_text("veri", encoding="utf-8")
    os.link(asil, tmp_path / "bag.txt")
    kopru = _Kopru()
    sonuc = await _yukle(ToolContext(root=tmp_path, chrome=kopru), "bag.txt")
    assert not sonuc.ok and "hard link" in sonuc.output and kopru.cagrilar == []


async def test_okuma_engelli_yol_yuklenmez(tmp_path):
    gizli = tmp_path / "gizli"
    gizli.mkdir()
    (gizli / "rapor.pdf").write_bytes(b"%PDF")
    policy = SandboxPolicy(deny_read=(gizli,))
    kopru = _Kopru()
    context = ToolContext(root=tmp_path, chrome=kopru, sandbox_policy=policy)
    sonuc = await _yukle(context, "gizli/rapor.pdf")
    assert not sonuc.ok and "deny_read" in sonuc.output and kopru.cagrilar == []


async def test_siradan_dosya_yuklenir(tmp_path):
    (tmp_path / "logo.png").write_bytes(b"\x89PNG")
    kopru = _Kopru()
    assert (await _yukle(ToolContext(root=tmp_path, chrome=kopru), "logo.png")).ok
