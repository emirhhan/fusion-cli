"""Tel ayar kanıtı sahte core process ile doğrulanır; model çağrısı yoktur."""

import json
import sys
from dataclasses import asdict

import pytest
from evals import live_drive
from evals.driver_config import ConfigReceipt
from evals.driver_engine import from_options
from evals.effective_config import project_effective

from .fakes import make_config
from .test_live_drive_engine_proof import settings


@pytest.mark.parametrize(
    "mode",
    [
        "valid",
        "pid",
        "digest",
        "malformed",
        "repeated",
        "missing",
        "late",
        "multiple",
        "malformed_second",
    ],
)
async def test_selected_config_receipt_stream_controls_comparison(tmp_path, monkeypatch, mode):
    args, _ = settings(tmp_path)
    engine = from_options(args)
    assert engine is not None
    root = engine.selection.source_root
    proof = {
        "pid": 0,
        "package_file": str(root / "src/fusion_cli/__init__.py"),
        "entry_file": str(root / "src/fusion_cli/cli/app.py"),
        "source_root": str(root),
        "source_digest": engine.source_digest,
        "requested_revision": engine.selection.requested_revision,
        "bootstrap_compatible": True,
        "revision_provenance": "unverified",
    }
    config = make_config()
    receipt = asdict(
        ConfigReceipt(
            1,
            0,
            engine.source_digest,
            engine.selection.requested_revision,
            "unverified",
            project_effective(config, config.agent, "general"),
        )
    )
    if mode == "digest":
        receipt["source_digest"] = "b" * 64
    if mode == "malformed":
        receipt["effective"]["digest"] = "c" * 64
    script = f"import os,json,sys\nproof={proof!r}\nreceipt={receipt!r}\n"
    script += "proof['pid']=os.getpid();receipt['pid']=os.getpid()\n"
    if mode == "pid":
        script += "receipt['pid']+=1\n"
    script += "print(json.dumps({'tip':'motor_kaniti','veri':proof}),flush=True)\n"
    script += "for line in sys.stdin:\n request=json.loads(line)\n"
    event = " print(json.dumps({'tip':'olay','veri':{'olay':'ModelCallStarted'}}),flush=True)\n"
    emit = (
        " print(json.dumps({'tip':'efektif_kanit','veri':"
        "{'sequence':1,'receipt':receipt}}),flush=True)\n"
    )
    if mode == "late":
        script += " if request['ad']=='tur.calistir':\n " + event + " " + emit
    elif mode != "missing":
        script += " if request['ad']=='tur.calistir':\n " + emit
        if mode == "repeated":
            script += " " + emit
        if mode == "multiple":
            script += " " + emit.replace("sequence':1", "sequence':2")
        if mode == "malformed_second":
            script += "  receipt['effective']['fields'][0]['kind']=[]\n"
            script += " " + emit.replace("sequence':1", "sequence':2")
        script += " " + event
    else:
        script += " if request['ad']=='tur.calistir':\n " + event
    script += (
        " print(json.dumps({'tip':'sonuc','id':request['id'],'veri':{'ok':True}}),flush=True)\n"
    )
    monkeypatch.setattr(live_drive, "_komut", lambda args: [sys.executable, "-c", script])
    result = await live_drive.drive(args, None)
    assert result["kontrollu_ayar_kaniti"] is (mode in {"valid", "multiple"}), result
    if mode not in {"valid", "multiple"}:
        assert result.get("hata")
        assert not result["turlar"][0]["ok"]


async def test_actual_fixture_installs_observer_in_proven_child(tmp_path):
    import hashlib

    args, _ = settings(tmp_path)
    package = tmp_path / "engine/src/fusion_cli"
    sources = {
        "config/__init__.py": "",
        "config/models.py": "class Config: pass\n",
        "core/__init__.py": "",
        "core/types.py": "class ModelSpec: pass\n",
        "engines/__init__.py": "",
        "engines/agent/__init__.py": "",
        "engines/agent/loop.py": (
            "def select_agent_spec(config, task_type, requirements=None):\n return config.agent\n"
        ),
        "cli/session.py": (
            "from fusion_cli.engines.agent import loop\n"
            "async def run_agent_task(task, config, *, task_type='general'):\n"
            " return loop.select_agent_spec(config, task_type, requirements=object())\n"
        ),
        "cli/app.py": (
            "import asyncio,json,sys\n"
            "from types import SimpleNamespace\n"
            "from fusion_cli.cli import session\n"
            "def main():\n"
            " for line in sys.stdin:\n"
            "  request=json.loads(line)\n"
            "  if request['ad']=='tur.calistir':\n"
            "   model=SimpleNamespace(name='fixture',model='fixture/model',tags=(),fallback=())\n"
            "   embedding=SimpleNamespace(provider='fixture',model='fixture/embed')\n"
            "   config=SimpleNamespace(agent=model,judge=model,candidates=(),\n"
            "    task_model_map={},embedding=embedding)\n"
            "   assert asyncio.run(session.run_agent_task('task',config)) is model\n"
            "  reply={'tip':'sonuc','id':request['id'],'veri':{'ok':True}}\n"
            "  print(json.dumps(reply),flush=True)\n"
        ),
    }
    for name, text in sources.items():
        path = package / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    manifest["sources"] = [
        {
            "path": p.relative_to(package.parent.parent).as_posix(),
            "digest": hashlib.sha256(p.read_bytes()).hexdigest(),
        }
        for p in sorted(package.rglob("*.py"))
    ]
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    assert "evals.driver_engine" in " ".join(live_drive._komut(args))
    result = await live_drive.drive(args, None)
    assert result["kontrollu_ayar_kaniti"], result
    receipt = result["efektif_kanitlar"][0]
    assert receipt["pid"] == result["motor_kaniti"]["pid"]
    assert receipt["source_digest"] == result["motor_kaniti"]["source_digest"]
    assert receipt["effective"]["authentication_status"] == "unknown"


@pytest.mark.parametrize("bad", [[], {}, True])
def test_wire_field_kind_type_is_explicitly_rejected(bad):
    from evals.driver_config import validate_wire
    from evals.engine_proof import ImportedEngineProof

    config = make_config()
    proof = ImportedEngineProof(123, "", "", "", "a" * 64, "b" * 40)
    raw = asdict(
        ConfigReceipt(
            1,
            123,
            proof.source_digest,
            proof.requested_revision,
            "unverified",
            project_effective(config, config.agent, "general"),
        )
    )
    raw["effective"]["fields"][0]["kind"] = bad
    with pytest.raises(ValueError):
        validate_wire(json.loads(json.dumps(raw)), proof)
