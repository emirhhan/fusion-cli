"""`codex exec` sağlayıcısı: iptalde süreç sızmaz, araç/görsel yeteneği dürüst bildirilir.

Ölçüldü (30 Ekim): yalnız `TimeoutError` yakalanıyordu; kullanıcı turu durdurunca
(`CancelledError`) `codex exec` çalışmaya devam edip abonelik kotasını harcıyordu ve
`kill()` sonrası `wait()` yoktu (P1-12). Araç şemaları/sonuçları iletilmediği halde
bilinmeyen model 'araç yetenekli' sayılıyordu.
"""

from __future__ import annotations

import asyncio

import pytest

from fusion_cli.core.types import CompletionRequest, Message, ModelSpec
from fusion_cli.providers import codex_cli
from fusion_cli.providers.capabilities import capabilities_for
from fusion_cli.providers.codex_cli import CodexCliProvider


class _Surec:
    returncode: int | None = None

    def __init__(self) -> None:
        self.oldu = False
        self.beklendi = False

    async def communicate(self, input=None):
        await asyncio.sleep(3600)

    def kill(self) -> None:
        self.oldu = True

    async def wait(self) -> int:
        self.beklendi = True
        return -9


@pytest.fixture
def surec(monkeypatch):
    proc = _Surec()

    async def sahte(*args, **kwargs):
        return proc

    monkeypatch.setattr(codex_cli, "codex_binary", lambda: "/bin/codex")
    monkeypatch.setattr(codex_cli, "codex_ready", lambda: True)
    monkeypatch.setattr(codex_cli.asyncio, "create_subprocess_exec", sahte)
    return proc


def _istek(timeout_s: float = 5.0) -> CompletionRequest:
    return CompletionRequest((Message("user", "x"),), 0.0, 16, timeout_s)


async def test_iptal_edilen_tur_codex_surecini_oldurur_ve_bekler(surec) -> None:
    gorev = asyncio.create_task(CodexCliProvider("codex_cli/default").complete(_istek()))
    await asyncio.sleep(0.05)

    gorev.cancel()
    with pytest.raises(asyncio.CancelledError):
        await gorev

    assert surec.oldu and surec.beklendi


async def test_zaman_asiminda_surec_olur_ve_beklenir(surec) -> None:
    sonuc = await CodexCliProvider("codex_cli/default").complete(_istek(0.05))

    assert not sonuc.ok and "zaman aşımı" in (sonuc.error or "")
    assert surec.oldu and surec.beklendi


def test_arac_sonucu_ve_arac_cagrisi_isteme_etiketli_girer() -> None:
    from fusion_cli.core.types import ToolCall

    istem = codex_cli._render_prompt(
        CompletionRequest(
            (
                Message("user", "dosyayı oku"),
                Message("assistant", "", tool_calls=(ToolCall("c1", "read_file", '{"p": 1}'),)),
                Message("tool", "içerik", tool_call_id="c1", name="read_file", ok=True),
            ),
            0.0,
            16,
            5,
        )
    )

    assert "[ARAÇ SONUCU read_file]" in istem
    assert "read_file" in istem and "içerik" in istem


def test_codex_modeli_arac_ve_gorsel_yetenekli_sayilmaz() -> None:
    kabiliyet = capabilities_for(ModelSpec(name="agent", model="codex_cli/default"))

    assert not kabiliyet.tools and not kabiliyet.native_tools and not kabiliyet.images
