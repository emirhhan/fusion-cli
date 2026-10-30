from __future__ import annotations

import json

from typer.testing import CliRunner

from fusion_cli import __version__
from fusion_cli.cli.app import app
from fusion_cli.runtime_health import collect_runtime_health


def test_runtime_health_surumu_ve_paket_kaynaklarini_dogrular():
    health = collect_runtime_health()

    assert health.version == __version__
    assert health.python
    assert health.platform
    assert health.resources_ok is True


def test_runtime_health_json_sozlesmesi_stdoutu_kirletmez():
    result = CliRunner().invoke(app, ["runtime-health", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "ok": True,
        "platform": payload["platform"],
        "python": payload["python"],
        "resources_ok": True,
        "version": __version__,
    }


def test_cevrimdisi_tokenizer_indirme_hatasi_denetimi_cokertmez(monkeypatch):
    """Ölçüldü (30 Ekim): BPE önbellekte yokken ağ hatası (OSError) yakalanmıyordu (E1-40)."""
    import tiktoken

    from fusion_cli import runtime_health

    def _ag_yok(name):
        raise ConnectionError("ağ yok")

    monkeypatch.setattr(tiktoken, "get_encoding", _ag_yok)

    assert runtime_health._tokenizer_plugins_ok() is False
    assert runtime_health.collect_runtime_health().resources_ok is False
