"""Masaüstü (AppSession) yüzeyinde /worktree, /rewind, sohbet.adlandir ve günlük temizliği.

Ölçüldü (31 Ekim, bağımsız inceleme): `/worktree` sonrası `_adopt_state_root` geçmişi YENİ
kökün transcript'inden yeniden yüklüyor ve sohbet boşalıyordu; `/rewind` arayüze geri sarma
sinyali döndürmüyordu; `enter_worktree` aracının isteği masaüstünde hiç tüketilmiyordu;
`state.worktree` kök değişiminde yeniden türetilmiyordu. AppSession seviyesinde test yoktu.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.appserver.workspace_journal import OWNER_AGENT, UndoEntry
from fusion_cli.cli.repl.transcript_store import list_conversations, load_transcript_messages
from fusion_cli.core.types import Message

pytestmark = pytest.mark.asyncio


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "depo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "fusion@test.local")
    _git(root, "config", "user.name", "Fusion Test")
    (root / "app.txt").write_text("taban\n", encoding="utf-8")
    _git(root, "add", "app.txt")
    _git(root, "commit", "-qm", "taban")
    return root


@pytest.fixture
def memory(tmp_path: Path, monkeypatch) -> Path:
    from fusion_cli.config.loader import load_config

    memory_dir = tmp_path / "memory"
    config = replace(load_config(), memory_dir=memory_dir)
    monkeypatch.setattr("fusion_cli.appserver.session.load_config", lambda: config)
    return memory_dir


async def _session(repo: Path, tmp_path: Path, lines: list[str]) -> AppSession:
    oturum = AppSession(lines.append, root=repo, home=tmp_path / "ev")
    await oturum.handle(Request(id="b", name="oturum.baslat", data={"sohbet_id": "sekme-1"}))
    oturum._transcript_store.record_user("merhaba")
    oturum._transcript_store.record_assistant("selam")
    oturum._state.history = [Message("user", "merhaba"), Message("assistant", "selam")]
    return oturum


async def test_worktree_komutu_gecmisi_korur_ve_ayni_sohbete_yazar(repo, tmp_path, memory):
    lines: list[str] = []
    oturum = await _session(repo, tmp_path, lines)
    oturum._state.checkpoints.begin("merhaba", [])
    try:
        sonuc = await oturum._dispatch(
            Request("w", "komut.calistir", {"ad": "worktree", "arguman": "ozellik"})
        )
        agac = repo / ".claude" / "worktrees" / "ozellik"
        assert sonuc["ok"] and sonuc["kok"] == str(agac.resolve())
        assert [m.content for m in oturum._state.history] == ["merhaba", "selam"], "geçmiş kaybı"
        assert oturum._state.worktree is not None and oturum._state.worktree.name == "ozellik"
        assert len(oturum._state.checkpoints.entries()) == 1, "tur kayıtları aynı sohbetin"

        # Ağaçtayken yazılanlar AYNI sohbete gider: proje kökünden de, ağaçtan da görünür.
        oturum._transcript_store.record_user("ikinci")
        beklenen = ["merhaba", "selam", "ikinci"]
        assert [
            m.content for m in load_transcript_messages(memory, repo, conversation_id="sekme-1")
        ] == beklenen
        assert [
            m.content for m in load_transcript_messages(memory, agac, conversation_id="sekme-1")
        ] == beklenen
        assert [ref.conversation_id for ref in list_conversations(memory, agac)] == ["sekme-1"]

        cikis = await oturum._dispatch(
            Request("c", "komut.calistir", {"ad": "worktree", "arguman": "cik"})
        )
        assert cikis["kok"] == str(repo.resolve()) and "kaldırıldı" in cikis["metin"]
        assert oturum._state.worktree is None
        assert [m.content for m in oturum._state.history] == ["merhaba", "selam"]
    finally:
        await oturum.close()


async def test_oturum_baslat_koku_state_worktree_yi_yeniden_turetir(repo, tmp_path, memory):
    from fusion_cli.core.worktree import enter_worktree

    agac = enter_worktree(repo, "hazir")
    baska = tmp_path / "baska"
    baska.mkdir()
    lines: list[str] = []
    oturum = AppSession(lines.append, root=repo, home=tmp_path / "ev")
    try:
        await oturum.handle(Request(id="1", name="oturum.baslat", data={"kok": str(agac.path)}))
        assert oturum._state.worktree is not None and oturum._state.worktree.name == "hazir"
        assert (
            "hazir"
            in (await oturum._dispatch(Request("w", "komut.calistir", {"ad": "worktree"})))["metin"]
        )

        await oturum.handle(Request(id="2", name="oturum.baslat", data={"kok": str(baska)}))
        assert oturum._state.worktree is None, "başka projeye geçince eski künye kalmaz"
        cikis = await oturum._dispatch(
            Request("c", "komut.calistir", {"ad": "worktree", "arguman": "cik"})
        )
        assert cikis["metin"] == "Bir çalışma ağacında değilsin."
        assert oturum._root == baska and agac.path.exists()
    finally:
        await oturum.close()


async def test_rewind_konusma_arayuze_kalan_gecmisi_doner(repo, tmp_path, memory):
    lines: list[str] = []
    oturum = await _session(repo, tmp_path, lines)
    dosya = repo / "a.txt"
    try:
        for ad in ("bir", "iki"):
            checkpoint = oturum._state.checkpoints.begin(ad, oturum._state.history)
            checkpoint.changes.record(dosya)
            dosya.write_text(ad, encoding="utf-8")
            checkpoint.changes.record_applied(dosya)
            oturum._state.history = [
                *oturum._state.history,
                Message("user", ad),
                Message("assistant", f"a-{ad}"),
            ]
            oturum._transcript_store.record_user(ad)
            oturum._transcript_store.record_assistant(f"a-{ad}")
        oturum._workspace_journal.record(
            UndoEntry("a.txt", True, b"bir", b"iki", "", 1, 1, owner=OWNER_AGENT)
        )

        sonuc = await oturum._dispatch(
            Request("r", "komut.calistir", {"ad": "rewind", "arguman": "2 konusma"})
        )
        assert [row["metin"] for row in sonuc["gecmis"]] == ["merhaba", "selam", "bir", "a-bir"]
        assert sonuc["gecmis"][0]["rol"] == "kullanici"
        assert "2. turun başına" in sonuc["metin"]
        # Claude Code (#200): hedef turun istemi masaüstünde de giriş kutusuna döner.
        assert sonuc["girdi"] == "iki"
        assert dosya.read_text(encoding="utf-8") == "iki", "yalnız konuşma: dosyalar kalır"

        yalniz_kod = await oturum._dispatch(
            Request("k", "komut.calistir", {"ad": "rewind", "arguman": "2 kod"})
        )
        assert "gecmis" not in yalniz_kod, "konuşma değişmedi; arayüz kesmesin"
        assert dosya.read_text(encoding="utf-8") == "bir"
        assert oturum._workspace_journal.latest() == [], "geri alınan girdi düşer"
    finally:
        await oturum.close()


async def test_sohbet_adlandir_acik_sekmeyi_ve_listeyi_gunceller(repo, tmp_path, memory):
    lines: list[str] = []
    oturum = await _session(repo, tmp_path, lines)
    try:
        bos = await oturum._dispatch(Request("x", "sohbet.adlandir", {"ad": "  "}))
        assert bos["ok"] is False and "Kullanım" in bos["metin"]

        sonuc = await oturum._dispatch(Request("a", "sohbet.adlandir", {"ad": "Deneme"}))
        assert sonuc == {"ok": True, "sohbet_id": "sekme-1", "ad": "Deneme"}
        assert oturum._state.conversation_name == "Deneme"
        liste = oturum._list_conversations()["sohbetler"]
        assert liste[0]["ad"] == "Deneme" and liste[0]["baslik"] == "Deneme"
        (ref,) = list_conversations(memory, repo)
        assert ref.name == "Deneme"
    finally:
        await oturum.close()


async def test_enter_worktree_araci_tur_sonunda_masaustu_kokunu_degistirir(
    repo, tmp_path, memory, monkeypatch
):
    """Araç isteği ToolContext.worktree_switch'e yazar; masaüstü tur bitince uygulamalı."""
    from fusion_cli.cli import session as cli_session
    from fusion_cli.engines.agent.loop import AgentOutcome
    from fusion_cli.tools.worktree_tools import enter_worktree_tool, exit_worktree_tool

    seen: dict[str, object] = {}

    async def fake_run_agent_task(task, config, *, root, worktree_switch=None, **kwargs):
        from fusion_cli.core.tools import ToolContext

        assert worktree_switch is not None, "masaüstü anahtarı vermeli"
        context = ToolContext(root=root, worktree_switch=worktree_switch)
        tool = exit_worktree_tool if task == "çık" else enter_worktree_tool
        result = await tool({"name": "ajan"}, context)
        seen[task] = result.output
        return AgentOutcome(final_text="tamam", messages=[Message("user", task)])

    monkeypatch.setattr(cli_session, "run_agent_task", fake_run_agent_task)
    lines: list[str] = []
    oturum = await _session(repo, tmp_path, lines)
    try:
        sonuc = await oturum._run_turn("ayrı worktree'de dene")
        agac = repo / ".claude" / "worktrees" / "ajan"
        assert sonuc["kok"] == str(agac.resolve()), sonuc
        assert "çalışma ağacına geçti" in sonuc["metin"]
        assert oturum._root == agac and oturum._state.worktree is not None

        cikis = await oturum._run_turn("çık")
        assert cikis["kok"] == str(repo.resolve()) and "kaldırıldı" in cikis["metin"]
        assert oturum._root == repo and oturum._state.worktree is None
    finally:
        await oturum.close()
    assert json.loads(lines[-1]) is not None
