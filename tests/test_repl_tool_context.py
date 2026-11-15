"""REPL turunun araç bağlamı yapılandırmadaki araç ayarlarını okumalı.

Ölçüldü (31 Ekim): `fusion` etkileşimli oturum kendi `ToolContext`'ini kurup `run_agent`'a
veriyordu; `runtime.desktop_screenshot_max_width: 1000` yazılsa da 1568 kullanılıyordu.
"""

from __future__ import annotations

from fusion_cli.cli.repl.loop import _turn_tool_context
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.cli.session import apply_runtime_settings
from fusion_cli.config.loader import load_config
from fusion_cli.core.tools import ToolContext
from fusion_cli.memory.factory import null_memory


def _config(tmp_path):
    hedef = tmp_path / "config.yaml"
    hedef.write_text(
        "runtime:\n  desktop_screenshot_max_width: 1000\n  desktop_exclude_fusion_window: false\n"
        "  shell_workspace_fingerprint: false\n",
        encoding="utf-8",
    )
    return load_config(hedef)


def test_repl_turu_masaustu_ayarlarini_yapilandirmadan_alir(tmp_path) -> None:
    state = ReplState(config=_config(tmp_path), memory=null_memory(), root=tmp_path, home=tmp_path)

    context = _turn_tool_context(state)

    assert context.root == tmp_path
    assert context.desktop_screenshot_max_width == 1000
    assert context.desktop_exclude_fusion_window is False
    assert context.shell_fingerprint is False


def test_ayarlar_verilen_baglamin_ustune_islenir(tmp_path) -> None:
    context = apply_runtime_settings(
        ToolContext(root=tmp_path, hidden_env=frozenset({"GIZLI"})), _config(tmp_path)
    )

    assert context.desktop_screenshot_max_width == 1000 and "GIZLI" in context.hidden_env
