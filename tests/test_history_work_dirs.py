"""Codex oturumunun çalıştığı klasörlerin bulunması."""

from __future__ import annotations

import json
from pathlib import Path

from fusion_cli.history.work_dirs import codex_work_dirs

SESSION = "01a15554-ddbf-7383-82de-134ed730ba37"


def _rollout(home: Path, satirlar: list[dict]) -> None:
    klasor = home / ".codex" / "sessions" / "2026" / "10" / "19"
    klasor.mkdir(parents=True)
    yol = klasor / f"rollout-2026-10-19T21-03-07-{SESSION}.jsonl"
    yol.write_text("\n".join(json.dumps(s) for s in satirlar), encoding="utf-8")


def _kur_gecmis(home: Path) -> None:
    import sqlite3

    baglanti = sqlite3.connect(home / ".codex" / "thread_history_1.sqlite")
    baglanti.execute(
        "CREATE TABLE thread_items (thread_id TEXT, turn_id TEXT, item_id TEXT, "
        "rollout_ordinal INTEGER, created_at_ms INTEGER, item_json TEXT, item_type TEXT)"
    )
    metin = json.dumps({"type": "userMessage", "content": [{"text": "Summertime çevir"}]})
    baglanti.execute(
        "INSERT INTO thread_items VALUES (?,?,?,?,?,?,?)",
        (SESSION, "t", "i1", 1, 0, metin, "userMessage"),
    )
    baglanti.commit()
    baglanti.close()
    kayit = {"id": SESSION, "thread_name": "Summertime", "updated_at": "2026-10-19T21:00:00Z"}
    (home / ".codex" / "session_index.jsonl").write_text(json.dumps(kayit), encoding="utf-8")


def _arac(komut: str) -> dict:
    return {"payload": {"type": "custom_tool_call", "input": komut}}


def test_arac_cagrilarindaki_proje_klasorlerini_sikliga_gore_dondurur(tmp_path):
    oyun = tmp_path / "Desktop" / "GetAll" / "summertimesaga"
    yama = tmp_path / "Desktop" / "Summertime-Turkce-Arayuz"
    oyun.mkdir(parents=True)
    yama.mkdir(parents=True)
    _rollout(
        tmp_path,
        [
            _arac(f"rg -n 'x' {oyun}/game/a.rpy"),
            _arac(f"ls {oyun}/game"),
            _arac(f"cat {yama}/BILGI.txt"),
        ],
    )

    assert codex_work_dirs(tmp_path, SESSION) == (tmp_path / "Desktop" / "GetAll", yama)


def test_cwd_masaustunun_kendisi_ve_gizli_klasorler_dislanir(tmp_path):
    (tmp_path / "Desktop").mkdir()
    (tmp_path / ".codex" / "memories").mkdir(parents=True)
    _rollout(
        tmp_path,
        [
            {"payload": {"cwd": f"file://{tmp_path}/Desktop"}},
            _arac(f"cat {tmp_path}/.codex/memories/a.md; ls {tmp_path}/Desktop"),
        ],
    )

    assert codex_work_dirs(tmp_path, SESSION) == ()


def test_var_olmayan_klasor_ve_dosya_yolu_atlanir(tmp_path):
    (tmp_path / "Desktop").mkdir()
    (tmp_path / "Desktop" / "not.txt").write_text("x", encoding="utf-8")
    _rollout(tmp_path, [_arac(f"cat {tmp_path}/Desktop/not.txt {tmp_path}/Desktop/yok/a.py")])

    assert codex_work_dirs(tmp_path, SESSION) == ()


def test_rollout_yoksa_bos_doner(tmp_path):
    assert codex_work_dirs(tmp_path, SESSION) == ()


def test_devralma_klasorleri_ve_kok_uyusmazligini_bildirir(tmp_path):
    from fusion_cli.appserver.history import PreparedResume, prepare_resume

    oyun = tmp_path / "Desktop" / "GetAll" / "summertimesaga"
    oyun.mkdir(parents=True)
    kok = tmp_path / "Desktop" / "VFS-BOT"
    kok.mkdir()
    _rollout(tmp_path, [_arac(f"ls {oyun}/game")])
    _kur_gecmis(tmp_path)

    sonuc = prepare_resume(tmp_path, kok, {"kaynak": "codex", "oturum_id": SESSION})

    assert isinstance(sonuc, PreparedResume)
    assert sonuc.work_dirs == (tmp_path / "Desktop" / "GetAll",)
    assert sonuc.payload["kok_uyusmuyor"] is True
    assert str(tmp_path / "Desktop" / "GetAll") in sonuc.digest
