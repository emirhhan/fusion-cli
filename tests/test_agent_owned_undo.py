"""Geri alma yalnız Fusion'ın yaptığı değişikliği kaldırır (S2-01).

Ölçüldü (28 Ekim): kayıt olmayan dosyada geri alma `git restore --source=HEAD`
çalıştırıyordu; kullanıcının commit'lenmemiş düzenlemesi kayboluyor, kullanıcının
yeni dosyası siliniyor ve sonuç "başarılı" dönüyordu. Artık geri alma ajan
turunun başındaki anlık görüntüye döner ve dosya o turdan sonra değiştiyse
çatışma bildirir.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.appserver.workspace import (
    WorkspaceJournal,
    list_changes,
    record_agent_changes,
    undo_entry,
)
from fusion_cli.core.changeset import ChangeSet


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _repo(root: Path) -> None:
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "fusion@test.local")
    _git(root, "config", "user.name", "Fusion Test")
    (root / "app.txt").write_text("taban\n", encoding="utf-8")
    _git(root, "add", "app.txt")
    _git(root, "commit", "-qm", "taban")


def _agent_writes(root: Path, journal: WorkspaceJournal, writes: dict[str, str]) -> None:
    """Ajan aracının yaptığı gibi: yazmadan önce anlık görüntü, sonra yaz."""
    changes = ChangeSet()
    for name, content in writes.items():
        changes.record(root / name)
        (root / name).write_text(content, encoding="utf-8")
    record_agent_changes(root, journal, changes.snapshots)


def test_undo_kullanicinin_onceki_duzenlemesini_korur(tmp_path):
    _repo(tmp_path)
    (tmp_path / "app.txt").write_text("taban\nkullanıcı satırı\n", encoding="utf-8")
    journal = WorkspaceJournal()
    _agent_writes(tmp_path, journal, {"app.txt": "taban\nkullanıcı satırı\najan satırı\n"})

    result = undo_entry(tmp_path, {"yol": "app.txt"}, journal)

    assert result["ok"] is True
    assert (tmp_path / "app.txt").read_text(encoding="utf-8") == "taban\nkullanıcı satırı\n"


def test_ajandan_sonra_degisen_dosyada_undo_catisma_doner(tmp_path):
    _repo(tmp_path)
    journal = WorkspaceJournal()
    _agent_writes(tmp_path, journal, {"app.txt": "ajan\n"})
    (tmp_path / "app.txt").write_text("ajan\nsonra kullanıcı\n", encoding="utf-8")

    result = undo_entry(tmp_path, {"yol": "app.txt"}, journal)

    assert result["ok"] is False
    assert result["kod"] == "CONFLICT"
    assert (tmp_path / "app.txt").read_text(encoding="utf-8") == "ajan\nsonra kullanıcı\n"


def test_kayitsiz_degisiklik_head_e_dondurulmez(tmp_path):
    _repo(tmp_path)
    (tmp_path / "app.txt").write_text("commitlenmemiş kullanıcı işi\n", encoding="utf-8")
    (tmp_path / "kullanici-yeni.txt").write_text("kullanıcının dosyası\n", encoding="utf-8")
    journal = WorkspaceJournal()

    tracked = undo_entry(tmp_path, {"yol": "app.txt"}, journal)
    untracked = undo_entry(tmp_path, {"yol": "kullanici-yeni.txt"}, journal)

    assert tracked["ok"] is False and tracked["kod"] == "NOT_OWNED"
    assert untracked["ok"] is False and untracked["kod"] == "NOT_OWNED"
    assert (tmp_path / "app.txt").read_text(encoding="utf-8") == "commitlenmemiş kullanıcı işi\n"
    assert (tmp_path / "kullanici-yeni.txt").exists()


def test_degisiklik_listesi_yalniz_sahipli_dosyayi_geri_alinabilir_gosterir(tmp_path):
    _repo(tmp_path)
    (tmp_path / "kullanici.txt").write_text("kullanıcı\n", encoding="utf-8")
    journal = WorkspaceJournal()
    _agent_writes(tmp_path, journal, {"app.txt": "ajan\n", "ajan-yeni.txt": "yeni\n"})

    result = list_changes(tmp_path, journal)

    durum = {item["yol"]: item["geri_alinabilir"] for item in result["degisiklikler"]}
    assert durum == {"app.txt": True, "ajan-yeni.txt": True, "kullanici.txt": False}


def test_ajanin_yarattigi_dosya_yalniz_icerigi_ayniysa_silinir(tmp_path):
    journal = WorkspaceJournal()
    _agent_writes(tmp_path, journal, {"yeni.txt": "ajan\n"})
    (tmp_path / "yeni.txt").write_text("kullanıcı doldurdu\n", encoding="utf-8")

    catisma = undo_entry(tmp_path, {"yol": "yeni.txt"}, journal)

    assert catisma["kod"] == "CONFLICT"
    assert (tmp_path / "yeni.txt").exists()

    (tmp_path / "yeni.txt").write_text("ajan\n", encoding="utf-8")
    geri = undo_entry(tmp_path, {"yol": "yeni.txt"}, journal)

    assert geri["ok"] is True
    assert not (tmp_path / "yeni.txt").exists()


def test_crlf_bom_ve_binary_icerik_bayt_bayt_geri_doner(tmp_path):
    once = {"crlf.txt": b"\xef\xbb\xbfsatir1\r\nsatir2\r\n", "veri.bin": b"\x00\x01\xff"}
    for name, raw in once.items():
        (tmp_path / name).write_bytes(raw)
    journal = WorkspaceJournal()
    changes = ChangeSet()
    for name in once:
        changes.record(tmp_path / name)
    (tmp_path / "crlf.txt").write_bytes(b"degisti\n")
    (tmp_path / "veri.bin").write_bytes(b"\x02")
    record_agent_changes(tmp_path, journal, changes.snapshots)

    for name, raw in once.items():
        assert undo_entry(tmp_path, {"yol": name}, journal)["ok"] is True
        assert (tmp_path / name).read_bytes() == raw


def test_ajanin_sildigi_dosya_geri_getirilir(tmp_path):
    (tmp_path / "eski.txt").write_text("içerik\n", encoding="utf-8")
    journal = WorkspaceJournal()
    changes = ChangeSet()
    changes.record(tmp_path / "eski.txt")
    (tmp_path / "eski.txt").unlink()
    record_agent_changes(tmp_path, journal, changes.snapshots)

    assert undo_entry(tmp_path, {"yol": "eski.txt"}, journal)["ok"] is True
    assert (tmp_path / "eski.txt").read_text(encoding="utf-8") == "içerik\n"


async def test_uygulama_turu_ajanin_degisikliklerini_gunluge_yazar(tmp_path, monkeypatch):
    """Tur bittiğinde ChangeSet günlüğe geçmezse UI geri alma ajanı hiç göremez."""
    from fusion_cli.cli import session as cli_session
    from fusion_cli.engines.agent.loop import AgentOutcome

    (tmp_path / "app.txt").write_text("önce\n", encoding="utf-8")

    async def fake_run_agent_task(task, config, *, root, changes, **kwargs):
        changes.record(root / "app.txt")
        (root / "app.txt").write_text("ajan\n", encoding="utf-8")
        return AgentOutcome(final_text="tamam", messages=[])

    monkeypatch.setattr(cli_session, "run_agent_task", fake_run_agent_task)
    lines: list[str] = []
    session = AppSession(lines.append, root=tmp_path, home=tmp_path.parent / ".ev")
    try:
        await session._run_turn("dosyayı yaz")
        await session.handle(Request(id="geri", name="proje.geri_al", data={"yol": "app.txt"}))
    finally:
        await session.close()

    sonuc = json.loads(lines[-1])["veri"]
    assert sonuc["ok"] is True, sonuc
    assert (tmp_path / "app.txt").read_text(encoding="utf-8") == "önce\n"
