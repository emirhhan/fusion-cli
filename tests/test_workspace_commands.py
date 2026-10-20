"""`/cop`, `/trace`, `/add-dir`: terminal alt komutlarının slash karşılıkları.

Slash komutları masaüstü uygulamasında da aynı defterden çalışır; bu üç özellik
eskiden yalnız terminalde (`fusion cop`, `fusion trace`, `--add-dir`) vardı.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.appserver.commands import run_command
from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.loader import load_config
from fusion_cli.core.events import StatusChanged
from fusion_cli.memory.factory import null_memory
from fusion_cli.observability.trace_store import TraceStore
from fusion_cli.tools.safe_delete import move_to_trash


@pytest.fixture
def state(tmp_path: Path) -> ReplState:
    source = tmp_path / "config.yaml"
    source.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    root = tmp_path / "proje"
    root.mkdir()
    return ReplState(
        config=load_config(source), memory=null_memory(), root=root, home=tmp_path / "ev"
    )


def _run(state: ReplState, name: str, argument: str = "") -> str:
    return str(run_command(build_registry(), state, name, argument)["metin"])


def test_cop_listeler_ve_geri_alir(state, tmp_path, monkeypatch):
    cop = tmp_path / "cop"
    monkeypatch.setattr("fusion_cli.cli.repl.workspace_commands.trash_dir", lambda: cop)
    assert _run(state, "cop") == "Fusion çöpü boş."
    dosya = state.root / "not.txt"
    dosya.write_text("x")
    tasinan, _ = move_to_trash(
        ("not.txt",), cwd=state.root, root=state.root, home=tmp_path, trash_root=cop
    )
    liste = _run(state, "cop")
    assert tasinan[0].id in liste and str(dosya) in liste
    assert not dosya.exists()
    assert _run(state, "cop", f"geri-al {tasinan[0].id}") == f"Geri alındı: {dosya}"
    assert dosya.read_text() == "x"
    assert "böyle bir girdi yok" in _run(state, "cop", "geri-al yok")


def test_trace_son_kosuyu_ozetler(state):
    assert "Henüz koşu kaydı yok" in _run(state, "trace")
    store = TraceStore(state.config.memory_dir / "traces")
    yazici = store.writer("20261009-120000-000000")
    yazici.handle(StatusChanged("başladı"))
    yazici.close()
    metin = _run(state, "trace")
    assert metin.startswith("20261009-120000-000000")
    assert "model çağrısı" in metin
    assert "20261009-120000-000000" in _run(state, "trace", "liste")
    assert "Böyle bir koşu yok" in _run(state, "trace", "uydurma")


def test_add_dir_acar_listeler_ve_kapatir(state, tmp_path):
    ek = tmp_path / "ortak"
    ek.mkdir()
    assert "Ek klasör yok" in _run(state, "add-dir")
    assert "Erişim açıldı" in _run(state, "add-dir", str(ek))
    assert state.extra_roots == (ek.resolve(),)
    assert "Zaten açık" in _run(state, "add-dir", str(ek))
    assert str(ek.resolve()) in _run(state, "add-dir")
    assert "proje kökünün içinde" in _run(state, "add-dir", str(state.root))
    assert "bulunamadı" in _run(state, "add-dir", str(tmp_path / "yok"))
    assert "ev dizininin" in _run(state, "add-dir", str(Path.home()))
    assert "kapatıldı" in _run(state, "add-dir", f"kaldir {ek}")
    assert state.extra_roots == ()
