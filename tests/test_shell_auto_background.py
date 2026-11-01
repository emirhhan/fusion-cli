"""Claude Code: zaman aşımına uğrayan ön plan komutu arka plana taşınır (#319).

Belge (tools-reference, "Foreground commands that move to the background"): komut
durdurulmaz; sonuç 'moved to the background' der, görev kimliği ve çıktı dosyası gelir.
`sleep` ile başlayan komutlar ve `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` hariç.
"""

from __future__ import annotations

import re
import time

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import shell
from fusion_cli.tools.jobs import job_status


def _kimlik(cikti: str) -> str:
    bulunan = re.search(r"iş kimliği: ([a-f0-9]{8})", cikti)
    assert bulunan, cikti
    return bulunan.group(1)


def test_zaman_asimi_komutu_oldurmez_arka_plana_tasir(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_DISABLE_BACKGROUND_TASKS", raising=False)
    context = ToolContext(root=tmp_path, shell_fingerprint=False)
    sonuc = shell.run_shell(
        {"command": "echo basladi; sleep 2; echo bitti; exit 3", "timeout": 600}, context
    )
    assert sonuc.ok, sonuc.output
    assert "arka plana taşındı" in sonuc.output
    kimlik = _kimlik(sonuc.output)
    gunluk = tmp_path / ".fusion" / "is" / f"{kimlik}.log"
    assert str(gunluk) in sonuc.output
    assert "basladi" in sonuc.output  # o ana kadarki çıktı da görünür
    durum = job_status({"id": kimlik, "wait_s": 10}, context)
    assert "BİTTİ (çıkış kodu 3)" in durum.output, durum.output
    metin = gunluk.read_text(encoding="utf-8")
    assert "basladi" in metin and "bitti" in metin


def test_tasinan_is_job_status_ile_durdurulabilir(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_DISABLE_BACKGROUND_TASKS", raising=False)
    context = ToolContext(root=tmp_path, shell_fingerprint=False)
    sonuc = shell.run_shell({"command": "echo x; sleep 30 ; echo y", "timeout": 500}, context)
    kimlik = _kimlik(sonuc.output)
    durdur = job_status({"id": kimlik, "stop": True}, context)
    assert durdur.ok, durdur.output
    assert "durduruldu" in durdur.output


def test_sleep_ile_baslayan_komut_eskisi_gibi_durdurulur(tmp_path):
    context = ToolContext(root=tmp_path, shell_fingerprint=False)
    basla = time.monotonic()
    sonuc = shell.run_shell({"command": "sleep 5", "timeout": 400}, context)
    assert not sonuc.ok and "durduruldu" in sonuc.output
    assert time.monotonic() - basla < 4
    assert not (tmp_path / ".fusion" / "is").exists()


def test_arka_plan_kapaliysa_tasinmaz(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_DISABLE_BACKGROUND_TASKS", "1")
    context = ToolContext(root=tmp_path, shell_fingerprint=False)
    sonuc = shell.run_shell({"command": "echo a; sleep 5", "timeout": 400}, context)
    assert not sonuc.ok and "durduruldu" in sonuc.output
    assert not (tmp_path / ".fusion" / "is").exists()
