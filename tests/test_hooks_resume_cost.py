"""SessionStart `resume` maliyet alanları (#111)."""

from __future__ import annotations

import asyncio
import json
import shlex
import sys
import time
from pathlib import Path

import pytest

from fusion_cli.core.hooks.events import HookCommand, HookEvent, HookSet
from fusion_cli.engines.hooks.resume_cost import resume_fields
from fusion_cli.engines.hooks.session import HookSession


@pytest.fixture(autouse=True)
def _kancalar_acik(monkeypatch):
    monkeypatch.delenv("FUSION_HOOKS", raising=False)


def _transcript(path: Path, stamp: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"type": "user", "timestamp": stamp - 10, "message": {"role": "user", "content": []}},
        {"type": "assistant", "timestamp": stamp, "message": {"role": "assistant"}},
    ]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_cevap_iceren_dokumde_dort_alan(tmp_path):
    path = tmp_path / "d.jsonl"
    now = time.time()
    _transcript(path, now - 5400)
    fields = resume_fields(path, 30_000, "", now=now)
    assert fields == {
        "seconds_since_last_response": 5400,
        "context_tokens": 10_000,
        "prompt_cache_likely_expired": True,
        "estimated_cache_write_usd": 0.0,
    }
    assert resume_fields(path, 0, "", now=now - 5300)["prompt_cache_likely_expired"] is False


def test_cevapsiz_ya_da_dokumsuzde_alan_yok(tmp_path):
    path = tmp_path / "bos.jsonl"
    path.write_text(json.dumps({"type": "user", "timestamp": 1}) + "\n", encoding="utf-8")
    assert resume_fields(path, 100, "") == {}
    assert resume_fields(tmp_path / "yok.jsonl", 100, "") == {}
    assert resume_fields(None, 100, "") == {}


def test_bilinen_modelde_onbellek_yazma_maliyeti(tmp_path, monkeypatch):
    import litellm

    monkeypatch.setitem(
        litellm.model_cost, "deneme-model", {"cache_creation_input_token_cost": 0.000005}
    )
    path = tmp_path / "d.jsonl"
    _transcript(path, time.time())
    assert resume_fields(path, 300_000, "deneme-model")["estimated_cache_write_usd"] == 0.5


def test_resume_sessionstart_girdisinde_alanlar_startupta_yok(tmp_path):
    log = tmp_path / "girdi.jsonl"
    script = tmp_path / "k.py"
    script.write_text(
        f"import sys\nopen({str(log)!r}, 'a').write(sys.stdin.read().strip() + '\\n')\n",
        encoding="utf-8",
    )
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"
    hooks = HookSet((HookCommand(HookEvent.SESSION_START, "", command, 20.0),))
    session = HookSession(
        root=tmp_path, loader=lambda: hooks, transcript_dir=tmp_path / "dokum", session_id="s1"
    )
    session.context_chars = lambda: 9_000
    _transcript(tmp_path / "dokum" / "s1.jsonl", time.time() - 60)

    asyncio.run(session.start("startup"))
    session.restart("resume", reason="resume", session_id="s1")
    asyncio.run(session.start())

    startup, resumed = (json.loads(line) for line in log.read_text().splitlines())
    assert "context_tokens" not in startup
    assert resumed["source"] == "resume"
    assert resumed["context_tokens"] == 3_000
    assert resumed["prompt_cache_likely_expired"] is False


def test_son_cevaptan_sonra_ozetleme_varsa_onbellek_dolmus_sayilir(tmp_path):
    # Claude: "...or a later compaction replaced the cached conversation".
    path = tmp_path / "d.jsonl"
    now = time.time()
    _transcript(path, now - 10)
    boundary = {"type": "system", "subtype": "compact_boundary", "timestamp": now - 5}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(boundary) + "\n")
    assert resume_fields(path, 0, "", now=now)["prompt_cache_likely_expired"] is True


def test_post_compact_dokume_sinir_satiri_yazar(tmp_path):
    session = HookSession(
        root=tmp_path, loader=HookSet, transcript_dir=tmp_path / "dokum", session_id="s1"
    )
    session.record("assistant", "cevap")
    asyncio.run(session.post_compact("manual", "özet"))
    rows = [json.loads(line) for line in (tmp_path / "dokum" / "s1.jsonl").read_text().splitlines()]
    assert rows[-1]["type"] == "system" and rows[-1]["subtype"] == "compact_boundary"


def test_buyuk_dokumde_son_cevap_kuyruktan_bulunur(tmp_path):
    path = tmp_path / "d.jsonl"
    now = time.time()
    filler = json.dumps({"type": "user", "timestamp": 1, "message": {"content": "x" * 1000}})
    path.write_text((filler + "\n") * 2000, encoding="utf-8")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"type": "assistant", "timestamp": now - 7}) + "\n")
    assert resume_fields(path, 0, "", now=now)["seconds_since_last_response"] == 7


def test_sessionstart_kancasi_yoksa_maliyet_hesaplanmaz(tmp_path):
    calls: list[int] = []
    session = HookSession(
        root=tmp_path, loader=HookSet, transcript_dir=tmp_path / "dokum", session_id="s1"
    )
    session.context_chars = lambda: calls.append(1) or 0
    session.next_source = "resume"
    asyncio.run(session.start())
    assert calls == []
