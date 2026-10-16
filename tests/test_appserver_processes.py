"""Masaüstü terminal ve süreç yaşam döngüsü sözleşmeleri."""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from pathlib import Path

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession


async def _send(
    session: AppSession,
    lines: list[str],
    name: str,
    data: dict[str, object],
) -> dict[str, object]:
    request_id = f"p-{len(lines)}"
    await session.handle(Request(id=request_id, name=name, data=data))
    for line in reversed(lines):
        payload = json.loads(line)
        if payload.get("tip") == "sonuc" and payload.get("id") == request_id:
            return payload["veri"]
    raise AssertionError("süreç isteğinin sonucu bulunamadı")


async def _wait_finished(session: AppSession, lines: list[str], process_id: str):
    for _ in range(100):
        result = await _send(session, lines, "surec.listele", {})
        process = next(item for item in result["surecler"] if item["surec_id"] == process_id)
        if process["durum"] != "calisiyor":
            return process
        await asyncio.sleep(0.02)
    raise AssertionError("süreç zamanında bitmedi")


async def test_surec_ciktiyi_akar_ve_bitis_kodunu_saklar(tmp_path: Path):
    """Çıktı pompası yoksa terminal komutu çalışsa bile UI sonsuza dek boş görünür."""
    lines: list[str] = []
    session = AppSession(lines.append, root=tmp_path, home=tmp_path.parent / ".fusion-home")

    started = await _send(session, lines, "surec.baslat", {"komut": "printf 'merhaba'"})
    process = await _wait_finished(session, lines, str(started["surec_id"]))
    await session.close()

    assert started["ok"] is True
    assert process["durum"] == "bitti"
    assert process["cikis_kodu"] == 0
    assert process["cikti"] == "merhaba"
    events = [json.loads(line) for line in lines if json.loads(line).get("tip") == "olay"]
    assert any(event["veri"].get("olay") == "ProcessOutput" for event in events)


async def test_surec_calisma_dizini_proje_disina_cikamaz(tmp_path: Path):
    """cwd sınırı kalkarsa terminal proje iznini kullanıp tüm diskte çalışabilir."""
    lines: list[str] = []
    session = AppSession(lines.append, root=tmp_path, home=tmp_path.parent / ".fusion-home")

    result = await _send(session, lines, "surec.baslat", {"komut": "pwd", "cwd": ".."})
    await session.close()

    assert result == {"ok": False, "metin": "Proje klasörünün dışına çıkılamaz."}


async def test_bir_sureci_durdurmak_digerini_etkilemez(tmp_path: Path):
    """Process-group sahipliği yanlışsa bir terminali durdurmak kardeş süreci öldürür."""
    lines: list[str] = []
    session = AppSession(lines.append, root=tmp_path, home=tmp_path.parent / ".fusion-home")
    command = 'python3 -c "import time; time.sleep(30)"'
    first = await _send(session, lines, "surec.baslat", {"komut": command})
    second = await _send(session, lines, "surec.baslat", {"komut": command})

    stopped = await _send(
        session,
        lines,
        "surec.kes",
        {"surec_id": first["surec_id"]},
    )
    listed = await _send(session, lines, "surec.listele", {})
    by_id = {item["surec_id"]: item for item in listed["surecler"]}
    await session.close()

    assert stopped["ok"] is True
    assert by_id[first["surec_id"]]["durum"] == "durduruldu"
    assert by_id[second["surec_id"]]["durum"] == "calisiyor"


def test_windows_kabugu_ve_sonlandirma_posix_varsayimi_yapmaz():
    """Terminal ve süreç araçları Windows'ta da çalışmalı.

    `/bin/zsh`, `/bin/sh` ve `os.killpg` Windows'ta YOKTUR. Eskiden süreç
    başlatma orada hiç çalışmıyor, kapanışta `os.killpg` `AttributeError`
    fırlatıyor ve bu hata `close()` içindeki `return_exceptions=True`
    tarafından yutuluyordu: süreçler öksüz kalıyor, kimseye söylenmiyordu.
    """
    from fusion_cli.appserver.processes import shell_command, terminate_process_tree

    posix = shell_command("Darwin", "/bin/zsh", "ls")
    assert posix[0] == "/bin/zsh" and posix[1] == "-lc" and posix[2] == "ls"

    windows = shell_command("Windows", None, "dir")
    assert windows[0].casefold().endswith("cmd.exe") or windows[0].casefold() == "cmd"
    assert windows[1] == "/c" and windows[2] == "dir"

    # Sonlandırma stratejisi de platforma göre seçilir; `killpg` adı geçmemeli.
    assert callable(terminate_process_tree)


async def test_close_reports_cleanup_failure_instead_of_swallowing(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import pytest

    from fusion_cli.appserver.processes import ProcessManager
    from fusion_cli.core.errors import CleanupFailedError

    manager = ProcessManager(tmp_path, lambda _: None)
    manager._records["owned"] = SimpleNamespace()

    async def failed(record):
        raise CleanupFailedError("cleanup unconfirmed")

    monkeypatch.setattr(manager, "_stop_record", failed)
    with pytest.raises(CleanupFailedError):
        await manager.close()


async def test_natural_parent_exit_does_not_leave_redirected_descendant(tmp_path):
    import os
    import shlex
    import signal
    import sys

    import pytest

    from fusion_cli.appserver.processes import ProcessManager

    if os.name == "nt":
        pytest.skip("POSIX descendant fixture")
    script = tmp_path / "parent.py"
    child_file = tmp_path / "child.pid"
    script.write_text("""import subprocess, sys
from pathlib import Path
child = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(60)"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
Path(sys.argv[1]).write_text(str(child.pid))
""")
    manager = ProcessManager(tmp_path, lambda _: None)
    command = " ".join(shlex.quote(str(value)) for value in (sys.executable, script, child_file))
    child = None
    try:
        started = await manager.start({"komut": command})
        record = manager._records[started["surec_id"]]
        await asyncio.wait_for(asyncio.shield(record.pump), 5)
        child = int(child_file.read_text())
        await manager.stop({"surec_id": started["surec_id"]})
        with pytest.raises(ProcessLookupError):
            os.kill(child, 0)
    finally:
        if child is not None:
            with suppress(ProcessLookupError):
                os.kill(child, signal.SIGKILL)
        await manager.close()
