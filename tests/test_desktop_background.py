from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

from pytest import MonkeyPatch

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import desktop_background, native_desktop


async def test_arka_plan_araci_kimligi_ve_refi_dogrular(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    invoke = AsyncMock(return_value={"ok": True, "status": "executed"})
    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke)
    context = ToolContext(tmp_path)
    invalid = await desktop_background.desktop_background_action(
        {"window_id": True, "pid": 20, "action": "press", "ref": "ref"},
        context,
    )
    assert not invalid.ok
    invoke.assert_not_called()
    result = await desktop_background.desktop_background_action(
        {"window_id": 2, "pid": 20, "action": "press", "ref": "ref"},
        context,
    )
    assert result.ok
    invoke.assert_awaited_once_with(
        "action",
        {
            "kind": "window",
            "id": 2,
            "pid": 20,
            "request": {"ref": "ref", "action": "press", "value": ""},
        },
    )


async def test_eski_ref_hatasi_basari_olarak_gosterilmez(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        native_desktop.SwiftDesktop,
        "invoke",
        AsyncMock(
            return_value={
                "ok": False,
                "metin": "Hedef öğe değişti; yeniden incele.",
            }
        ),
    )
    result = await desktop_background.desktop_background_action(
        {"window_id": 2, "pid": 20, "action": "press", "ref": "eski"},
        ToolContext(tmp_path),
    )
    assert not result.ok
    assert "yeniden incele" in result.output


async def test_pencere_yakalama_gorseli_modele_aktarir(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    invoke = AsyncMock(
        return_value={
            "ok": True,
            "image": "data:image/png;base64,YWJj",
            "id": 2,
            "pid": 20,
        }
    )
    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke)
    result = await desktop_background.desktop_background_screenshot(
        {"window_id": 2, "pid": 20},
        ToolContext(tmp_path),
    )
    assert result.ok and result.images
    assert json.loads(result.output) == {"ok": True, "id": 2, "pid": 20}
    invoke.assert_awaited_once_with("snapshot", {"kind": "window", "id": 2, "pid": 20})


async def test_yardimci_kaynak_parmak_iziyle_bir_kez_derlenir(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

    async def compile_helper(
        arguments: list[str], wait_seconds: int, payload: bytes = b""
    ) -> bytes:
        assert arguments[0] == "/usr/bin/swiftc"
        await asyncio.to_thread(Path(arguments[-1]).write_bytes, b"yerel-yardimci")
        return b""

    process = AsyncMock(side_effect=compile_helper)
    monkeypatch.setattr(native_desktop, "_process", process)
    first = await native_desktop._executable()
    second = await native_desktop._executable()
    assert first == second
    assert process.await_count == 1


async def test_swift_pencere_numarasi_celisirse_geometri_geri_dususu_reddedilir(
    tmp_path: Path,
) -> None:
    """Üretimdeki saf Swift eşleştiricisi gerçek Swift çalışma zamanında sınanır."""
    import shutil
    import subprocess
    import sys

    import pytest

    swift = shutil.which("swift")
    if swift is None or sys.platform != "darwin":
        pytest.skip("Swift çalışma zamanı bu ortamda yok.")
    source = Path(__file__).parents[1] / "src/fusion_cli/tools/data/desktop_host.swift"
    content = await asyncio.to_thread(source.read_text)
    start = content.index("func canUseWindowFallback(")
    end = content.index("\nfunc targetWindow(", start)
    # Uygulamanın kullandığı fonksiyon aynen alınır; ayrı Python kopyası sınanmaz.
    program = (
        "import AppKit\n"
        + content[start:end]
        + """
let frame = CGRect(x: 10, y: 20, width: 300, height: 200)
precondition(!canUseWindowFallback(999, frame, "Aynı", frame, "Aynı"))
precondition(!canUseWindowFallback(2, frame, "Aynı", frame, "Aynı"))
precondition(canUseWindowFallback(nil, frame, "Aynı", frame, "Aynı"))
precondition(!canUseWindowFallback(nil, nil, "Aynı", frame, "Aynı"))
precondition(!canUseWindowFallback(nil, frame, "Başka", frame, "Aynı"))
print("pencere-kimligi-dogrulandi")
"""
    )
    target = tmp_path / "identity.swift"
    await asyncio.to_thread(target.write_text, program)
    result = await asyncio.to_thread(
        subprocess.run,
        [swift, str(target)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "pencere-kimligi-dogrulandi"
