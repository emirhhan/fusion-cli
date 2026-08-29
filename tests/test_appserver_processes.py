"""Masaüstü terminal ve süreç yaşam döngüsü sözleşmeleri."""

from __future__ import annotations

import asyncio
import json
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
    command = "python3 -c \"import time; time.sleep(30)\""
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
