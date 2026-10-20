"""Sürücü seçilmiş çocuk sürecin kanıtı gelmeden görev göndermemeli."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys

import pytest
from evals import live_drive
from evals.driver_engine import from_options


def settings(tmp_path):
    root = tmp_path / "engine"
    package = root / "src/fusion_cli"
    (package / "cli").mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "cli/__init__.py").write_text("")
    received = tmp_path / "received.jsonl"
    (package / "cli/app.py").write_text(
        "import json,sys\nfrom pathlib import Path\n"
        "def main():\n"
        " for line in sys.stdin:\n"
        "  request=json.loads(line)\n"
        f"  with Path({str(received)!r}).open('a') as f:f.write(json.dumps(request)+'\\n')\n"
        "  reply={'tip':'sonuc','id':request['id'],'veri':{'ok':True,'metin':'bitti'}}\n"
        "  print(json.dumps(reply),flush=True)\n"
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "requested_revision": "a" * 40,
                "sources": [
                    {
                        "path": path.relative_to(root).as_posix(),
                        "digest": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                    for path in sorted(package.rglob("*.py"))
                ],
            }
        )
    )
    work = tmp_path / "empty-work"
    work.mkdir()
    args = argparse.Namespace(
        kok=str(work),
        mod="auto",
        gorev=["üret"],
        sure=5,
        chrome="",
        onay="once",
        log=False,
        engine_source=str(root),
        engine_manifest=str(manifest),
        engine_proof=str(tmp_path / "proof.json"),
    )
    return args, received


async def test_selected_fixture_same_process_receipt_precedes_task(tmp_path):
    args, received = settings(tmp_path)
    assert "evals.driver_engine" in " ".join(live_drive._komut(args))
    result = await live_drive.drive(args, None)
    assert result["turlar"][0]["ok"], result
    assert result["motor_kaniti"]["pid"] == json.loads((tmp_path / "proof.json").read_text())["pid"]
    requests = [json.loads(line)["ad"] for line in received.read_text().splitlines()]
    assert requests == ["oturum.baslat", "tur.calistir"]


@pytest.mark.parametrize(
    "mode", ["missing", "pid", "source_digest", "source_root", "bootstrap_compatible", "duplicate"]
)
async def test_missing_or_malformed_receipt_blocks_every_request(tmp_path, monkeypatch, mode):
    args, received = settings(tmp_path)
    engine = from_options(args)
    assert engine is not None
    root = engine.selection.source_root
    payload = {
        "pid": 0,
        "package_file": str(root / "src/fusion_cli/__init__.py"),
        "entry_file": str(root / "src/fusion_cli/cli/app.py"),
        "source_root": str(root),
        "source_digest": engine.source_digest,
        "requested_revision": engine.selection.requested_revision,
        "bootstrap_compatible": True,
        "revision_provenance": "unverified",
    }
    if mode not in {"missing", "duplicate", "pid"}:
        payload[mode] = False if mode == "bootstrap_compatible" else "wrong"
    script = f"import json,sys,os\npayload={payload!r}\n"
    script += "payload['pid']=os.getpid()" + ("+1" if mode == "pid" else "") + "\n"
    script += "print(json.dumps({'tip':'motor_kaniti','veri':payload}),flush=True)\n"
    if mode == "duplicate":
        script += "print(json.dumps({'tip':'motor_kaniti','veri':payload}),flush=True)\n"
    script += "from pathlib import Path\n"
    script += f"for line in sys.stdin:Path({str(received)!r}).write_text(line)\n"
    if mode == "missing":
        script = "pass"
    monkeypatch.setattr(live_drive, "_komut", lambda args: [sys.executable, "-c", script])
    result = await live_drive.drive(args, None)
    assert result.get("hata")
    assert not result["turlar"]
    assert not received.exists()


def test_partial_engine_options_rejected_before_spawn(tmp_path):
    args, _ = settings(tmp_path)
    args.engine_manifest = ""
    with pytest.raises(ValueError):
        live_drive._komut(args)


def test_absent_engine_options_preserve_original_command():
    for logging in (False, True):
        args = argparse.Namespace(log=logging)
        expected = live_drive._LOG_LAUNCHER if logging else live_drive._TESHIS_LAUNCHER
        assert live_drive._komut(args) == [sys.executable, "-c", expected]


@pytest.mark.parametrize("reverse", [False, True])
async def test_duplicate_receipt_during_task_invalidates_success(tmp_path, reverse):
    args, received = settings(tmp_path)
    app = tmp_path / "engine/src/fusion_cli/cli/app.py"
    app.write_text(
        app.read_text().replace(
            "  reply=",
            "  if request['ad']=='tur.calistir':\n"
            "   proof=json.loads(Path(" + repr(args.engine_proof) + ").read_text())\n"
            "   print(json.dumps({'tip':'motor_kaniti','veri':proof}),flush=True)\n"
            "  reply=",
        )
    )
    if reverse:
        text = app.read_text()
        start = text.index("  if request['ad']=='tur.calistir':")
        end = text.index("  reply=", start)
        duplicate = text[start:end]
        text = text[:start] + text[end:]
        app.write_text(text + duplicate)
    manifest = tmp_path / "manifest.json"
    data = json.loads(manifest.read_text())
    for source in data["sources"]:
        if source["path"] == "src/fusion_cli/cli/app.py":
            source["digest"] = hashlib.sha256(app.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(data))
    assert "evals.driver_engine" in " ".join(live_drive._komut(args))
    result = await live_drive.drive(args, None)
    assert received.exists()
    assert result.get("hata")
    assert not result["turlar"][0]["ok"]
