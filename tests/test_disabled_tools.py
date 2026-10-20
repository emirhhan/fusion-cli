"""`runtime.disabled_tools`: kapatılan araç ve takma adı modele hiç sunulmaz."""

from __future__ import annotations

import pytest

from fusion_cli.config.loader import ConfigError, _build_runtime
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.engine_tools import build_agent_registry
from fusion_cli.engines.agent.loop import AgentDeps

from .fakes import AlwaysApprove, make_config


async def _alt_ajan(*args, **kwargs):  # pragma: no cover - çağrılmaz
    raise AssertionError("alt ajan çalışmamalı")


def _registry(tmp_path, **runtime):
    deps = AgentDeps(
        config=make_config(runtime=runtime),
        publisher=type("P", (), {"publish": lambda self, event: None})(),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )
    return build_agent_registry(deps, depth=0, run_agent=_alt_ajan)


def test_kapatilan_arac_ve_takma_adi_sunulmaz(tmp_path):
    acik = _registry(tmp_path)
    kapali = _registry(tmp_path, disabled_tools=("clone_site", "spawn_agent"))

    assert acik.get("clone_site") is not None and acik.get("invoke_subagent") is not None
    assert kapali.get("clone_site") is None
    assert kapali.get("spawn_agent") is None and kapali.get("invoke_subagent") is None
    assert kapali.get("read_file") is not None
    assert set(acik.names()) - set(kapali.names()) == {
        "clone_site",
        "spawn_agent",
        "invoke_subagent",
    }


def test_yapilandirmadan_liste_okunur_yanlis_tip_reddedilir():
    from importlib.resources import files

    import yaml

    from fusion_cli.config.loader import load_config  # noqa: F401 - içe aktarma sağlığı

    varsayilan = yaml.safe_load(files("fusion_cli.config").joinpath("defaults.yaml").read_text())
    runtime = {**varsayilan["runtime"], "disabled_tools": ["clone_site"]}

    assert _build_runtime(runtime).disabled_tools == ("clone_site",)
    # Tek metin tek elemanlı liste sayılır (yükleyicinin genel kuralı); sayı reddedilir.
    tek = _build_runtime({**varsayilan["runtime"], "disabled_tools": "clone_site"})
    assert tek.disabled_tools == ("clone_site",)
    with pytest.raises(ConfigError):
        _build_runtime({**varsayilan["runtime"], "disabled_tools": [3]})
