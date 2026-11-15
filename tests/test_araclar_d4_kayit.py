"""Kayıt defteri P2/P3 düzeltmeleri (T1-62, T2-17, T2-39)."""

from __future__ import annotations

import threading
import time

from fusion_cli.core.tools import Tool, ToolContext, ToolResult
from fusion_cli.tools import build_registry
from fusion_cli.tools.registry import ToolRegistry, _CancellationEvent


async def test_claude_adlari_ve_arguman_anahtarlari_eslenir(tmp_path):
    """T1-62: `Edit` + `file_path/old_string/new_string` (Claude Code alışkanlığı)."""
    (tmp_path / "a.txt").write_text("merhaba dünya\n", encoding="utf-8")
    registry = build_registry()
    context = ToolContext(root=tmp_path)
    await registry.execute("Read", {"file_path": "a.txt"}, context)  # tam okuma kaydı

    sonuc = await registry.execute(
        "Edit", {"file_path": "a.txt", "old_string": "dünya", "new_string": "evren"}, context
    )

    assert sonuc.ok, sonuc.output
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "merhaba evren\n"


async def test_windsurf_view_file_absolute_path(tmp_path):
    (tmp_path / "a.txt").write_text("x\n", encoding="utf-8")
    registry = build_registry()

    sonuc = await registry.execute(
        "view_file", {"AbsolutePath": str(tmp_path / "a.txt")}, ToolContext(root=tmp_path)
    )

    assert sonuc.ok, sonuc.output


async def test_run_shell_cmd_anahtari(tmp_path):
    registry = build_registry()

    sonuc = await registry.execute("Bash", {"cmd": "echo selam"}, ToolContext(root=tmp_path))

    assert "selam" in sonuc.output


async def test_sema_anahtari_varsa_ad_degistirilmez():
    """Aracın kendi şemasında olan anahtar eşlenmez (yanlış eşleme yapılmasın)."""
    alinan: dict = {}

    def calis(args, context):
        alinan.update(args)
        return ToolResult("ok")

    registry = ToolRegistry()
    registry.register(
        Tool(
            name="ozel",
            description="x",
            parameters={
                "type": "object",
                "properties": {"file_path": {"type": "string"}, "path": {"type": "string"}},
            },
            run=calis,
        )
    )

    await registry.execute("ozel", {"file_path": "a", "path": "b"}, ToolContext(root="."))

    assert alinan == {"file_path": "a", "path": "b"}


async def test_buyuk_kucuk_harf_ve_tire_normallestirilir(tmp_path):
    registry = build_registry()
    (tmp_path / "a.txt").write_text("x\n", encoding="utf-8")
    context = ToolContext(root=tmp_path)

    for ad in ("read-file", "ReadFile", "READ_FILE", "LS"):
        sonuc = await registry.execute(
            ad, {"path": "a.txt" if "ead" in ad.lower() else "."}, context
        )
        assert sonuc.ok, (ad, sonuc.output)


async def test_bilinmeyen_arac_mesaji_gizli_takma_adlari_listelemez(tmp_path):
    """T2-39: `advertised=False` takma adlar bağlamı şişirip modele gizli adları öğretmesin."""
    registry = build_registry()

    sonuc = await registry.execute("yok_boyle_arac", {}, ToolContext(root=tmp_path))

    assert not sonuc.ok
    assert "read_file" in sonuc.output
    assert "view_file" not in sonuc.output
    assert "execute_command" not in sonuc.output


def test_iptal_olayi_wait_ust_iptali_gorur():
    """T2-17: `wait()` yalnız kendi bayrağına bakıyordu; üst iptal uyuyan aracı uyandırmıyordu."""
    ust = threading.Event()
    olay = _CancellationEvent(ust)
    threading.Timer(0.1, ust.set).start()

    baslangic = time.monotonic()
    sonuc = olay.wait(5)

    assert sonuc is True
    assert time.monotonic() - baslangic < 2


def test_iptal_olayi_wait_zaman_asiminda_false_doner():
    olay = _CancellationEvent(threading.Event())

    assert olay.wait(0.1) is False


async def test_async_call_nesnesi_dogru_yoldan_calisir(tmp_path):
    class Arac:
        async def __call__(self, args, context):
            return ToolResult("async-ok")

    registry = ToolRegistry()
    registry.register(
        Tool(
            name="nesne",
            description="x",
            parameters={"type": "object", "properties": {}},
            run=Arac(),
        )
    )

    sonuc = await registry.execute("nesne", {}, ToolContext(root=tmp_path))

    assert sonuc.ok and sonuc.output == "async-ok"
