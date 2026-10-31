"""Masaüstü `arkaplan.*` / `esler.*` uçları (P-048, P-060)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.appserver.background_routes import BACKGROUND_ROUTES, dispatch_background
from fusion_cli.cli.repl import agent_link
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.core.background_tasks import TaskStatus
from fusion_cli.core.peers import InboundPolicy
from fusion_cli.memory.factory import null_memory
from fusion_cli.tools import agent_tasks

from .fakes import make_config


@pytest.fixture
def launches(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(agent_tasks, "spawn_detached", lambda argv, *rest: calls.append(argv) or 9)
    return calls


@pytest.fixture
def state(tmp_path: Path):
    value = ReplState(
        config=make_config(memory_dir=tmp_path / "bellek"),
        memory=null_memory(),
        root=tmp_path,
        home=tmp_path / "ev",
    )
    yield value
    agent_link.close_link(value)


def test_durum_masaustunu_deftere_kaydeder_ve_gorevleri_doner(state, launches):
    started = dispatch_background(state, "arkaplan.baslat", {"gorev": "rapor yaz", "ad": "rapor"})
    assert started["ok"] and started["gorev"]["name"] == "rapor"

    status = dispatch_background(state, "arkaplan.durum", {})
    assert status["ok"] and status["ben"]
    assert [item["name"] for item in status["gorevler"]] == ["rapor"]
    assert status["gorevler"][0]["durum_etiketi"] == "sırada"
    assert state.agent_link is not None and state.agent_link.peer.kind == "masaustu"


def test_cevap_mesaj_durdur_goster_sil(state, launches):
    store = agent_tasks.task_store(state.config.memory_dir)
    task = store.create("iş", root=state.root, name="isci")
    store.update(task.id, status=TaskStatus.NEEDS_INPUT, question="onay?")
    store.heartbeat(task.id)
    store.ask(task.id, "1", {"tur": "onay"})

    assert dispatch_background(state, "arkaplan.goster", {"id": "isci"})["soru"]["tur"] == "onay"
    assert dispatch_background(state, "arkaplan.cevapla", {"id": "isci", "cevap": "evet"})["ok"]
    assert store.take_answer(task.id, "1") == "evet"
    assert dispatch_background(state, "arkaplan.durdur", {"id": "isci"})["ok"]
    store.update(task.id, status=TaskStatus.COMPLETED)
    assert dispatch_background(state, "arkaplan.mesaj", {"id": "isci", "metin": "devam"})["ok"]
    assert launches
    store.update(task.id, status=TaskStatus.COMPLETED)
    assert dispatch_background(state, "arkaplan.sil", {"id": "isci"})["ok"]
    missing = dispatch_background(state, "arkaplan.goster", {"id": "isci"})
    assert missing["ok"] is False and "bulunamadı" in missing["metin"]


def test_gelen_mesaj_masaustunde_bekletilir_tura_al_etiketli_metin_doner(tmp_path):
    from dataclasses import replace

    config = make_config(memory_dir=tmp_path / "bellek")
    config = replace(config, runtime=replace(config.runtime, cross_session_inbound="accept"))
    state = ReplState(config=config, memory=null_memory(), root=tmp_path, home=tmp_path / "ev")
    me = dispatch_background(state, "arkaplan.durum", {})["ben"]
    registry = agent_tasks.peer_registry(config.memory_dir)
    other = registry.register(
        name="terminal",
        kind="repl",
        pid=1,
        root=tmp_path,
        conversation_id="c",
        inbound=InboundPolicy.HOLD,
    )
    registry.send(other, me, "testleri koştur")

    status = dispatch_background(state, "arkaplan.durum", {})
    assert status["bekleyen"] == [{"no": 1, "kimden": "terminal", "metin": "testleri koştur"}]
    assert status["oturumlar"][0]["ad"] == "terminal"
    taken = dispatch_background(state, "esler.al", {"no": 1})
    assert 'guvenilmez="evet"' in taken["tur_metni"]
    assert dispatch_background(state, "esler.reddet", {"no": 1})["ok"] is False
    sent = dispatch_background(state, "esler.gonder", {"hedef": "terminal", "metin": "tamam"})
    assert sent["ok"] and [m.text for m in registry.take(other.id)] == ["tamam"]
    agent_link.close_link(state)


def test_arac_sekmesinin_sonucu_sonraki_tura_teslim_edilir(state):
    store = agent_tasks.task_store(state.config.memory_dir)
    task = store.create("iş", root=state.root, owner="app")
    store.update(task.id, status=TaskStatus.COMPLETED, delivered=False)
    store.write_result(task.id, "bitti: 2 test eklendi")
    dispatch_background(state, "arkaplan.durum", {}, turn_owner="app")
    assert any("2 test eklendi" in block for block in state.pending_blocks)


def test_gecersiz_istek_ok_false_doner(state):
    assert dispatch_background(state, "arkaplan.baslat", {"gorev": " "})["ok"] is False
    assert dispatch_background(state, "esler.al", {"no": "1"})["ok"] is False
    assert "arkaplan.durum" in BACKGROUND_ROUTES


def test_girdi_bekleyen_gorev_satiri_soru_turunu_ve_secenekleri_tasir(state):
    store = agent_tasks.task_store(state.config.memory_dir)
    task = store.create("iş", root=state.root, name="soran")
    store.update(task.id, status=TaskStatus.NEEDS_INPUT, question="Hangi veritabanı?")
    store.heartbeat(task.id)
    store.ask(task.id, "1", {"tur": "soru", "ozet": "Hangi veritabanı?", "secenekler": ["pg"]})

    row = dispatch_background(state, "arkaplan.durum", {})["gorevler"][0]
    answered = dispatch_background(state, "arkaplan.cevapla", {"id": "soran", "cevap": "Postgres"})

    assert row["soru"]["tur"] == "soru" and row["soru"]["secenekler"] == ["pg"]
    assert answered["ok"] and store.take_answer(task.id, "1") == "Postgres"


def test_onay_bekleyen_goreve_serbest_metin_acik_hatayla_doner(state):
    store = agent_tasks.task_store(state.config.memory_dir)
    task = store.create("iş", root=state.root, name="onayci")
    store.ask(task.id, "1", {"tur": "onay", "ozet": "run_shell onayı"})

    result = dispatch_background(state, "arkaplan.cevapla", {"id": "onayci", "cevap": "Postgres"})

    assert result["ok"] is False and "evet" in result["metin"]
