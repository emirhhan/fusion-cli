"""An unrelated counter probe must not turn final verification into game acceptance."""

from __future__ import annotations

from dataclasses import replace

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.verification import build_verifier
from fusion_cli.engines.agent.web_tools import run_play_probe
from fusion_cli.tools import play_probe
from fusion_cli.tools.game_assets import AssetUsage
from fusion_cli.tools.play_probe import ProbeReport
from tests.fakes import make_config

COUNTER_HTML = """<!doctype html><html lang="tr"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Sayaç</title>
<style>body{font-family:system-ui;margin:2rem}main{max-width:32rem;margin:auto}
button{padding:1rem;margin:.5rem}output{display:block;font-size:2rem}</style></head>
<body><main><h1>Sayaç</h1><p>Bu sayaç yalnızca düğmelerle değişir.</p>
<output id="count">0</output><button id="increment">Artır</button>
<button id="reset">Sıfırla</button></main><script>
let n=0;const output=document.getElementById('count');
document.getElementById('increment').onclick=()=>output.textContent=++n;
document.getElementById('reset').onclick=()=>output.textContent=n=0;
</script></body></html>"""

NO_GAME_OBSERVATION = ProbeReport(
    (),
    60,
    None,
    None,
    None,
    None,
    visual_problems=("oyunda kendiliğinden hareket eden hiçbir şey yok",),
)


@pytest.mark.parametrize(
    ("task_kinds", "report", "registered"),
    [
        (set(), NO_GAME_OBSERVATION, False),
        ({"oyun"}, NO_GAME_OBSERVATION, True),
        (set(), replace(NO_GAME_OBSERVATION, state_before='{"state":"playing"}'), True),
        (set(), replace(NO_GAME_OBSERVATION, state_after='{"state":"playing"}'), True),
        (set(), replace(NO_GAME_OBSERVATION, restart_state='{"state":"playing"}'), True),
        (set(), replace(NO_GAME_OBSERVATION, canvas_kind="2d", canvas_changed=False), True),
        (set(), replace(NO_GAME_OBSERVATION, canvas_kind="webgl"), True),
        (set(), replace(NO_GAME_OBSERVATION, canvas_kind="unknown"), True),
        (set(), replace(NO_GAME_OBSERVATION, canvas_changed=True), True),
    ],
)
async def test_probe_registration_requires_game_context_or_actual_game_observation(
    tmp_path, monkeypatch, task_kinds, report, registered
):
    index = tmp_path / "index.html"
    index.write_text(COUNTER_HTML)
    context = ToolContext(root=tmp_path, task_kinds=task_kinds)

    async def measured_probe(_target, _keys):
        return report

    monkeypatch.setattr(play_probe, "probe_game", measured_probe)
    result = await run_play_probe({"target": "index.html"}, context)

    assert result.ok
    assert context.probed_games == ({index.as_uri()} if registered else set())
    if not registered:
        assert result.structured["game_probe"] == "not_applicable"
        assert result.structured["page_diagnostics"]["console_error_count"] == 0
        assert result.structured["page_diagnostics"]["raf_per_second"] == 60
        assert result.is_observation
        assert "kapsamı dışında" in result.output
        assert "kendiliğinden hareket" not in result.output
    else:
        # Missing hooks on actual game tasks and broken/static canvas games
        # retain the existing measurements and final-verifier registration.
        assert "Oyun sondası" in result.output


@pytest.mark.parametrize(
    ("report", "expected_ok", "visible"),
    [
        (
            replace(
                NO_GAME_OBSERVATION,
                console_errors=("ReferenceError: updateCounter is not defined",),
            ),
            False,
            "ReferenceError: updateCounter is not defined",
        ),
        (
            replace(
                NO_GAME_OBSERVATION,
                console_errors=("Failed to load resource (https://example.com/data.json)",),
            ),
            False,
            "Failed to load resource",
        ),
        (replace(NO_GAME_OBSERVATION, raf_per_second=3), False, "3/sn"),
        (
            replace(NO_GAME_OBSERVATION, ignored_resources=("favicon.ico bulunamadı",)),
            True,
            "favicon.ico bulunamadı",
        ),
        (
            replace(
                NO_GAME_OBSERVATION,
                asset_usage=AssetUsage(loaded=("https://example.com/logo.svg",), canvas2d=False),
            ),
            True,
            "https://example.com/logo.svg",
        ),
    ],
)
async def test_not_applicable_game_probe_preserves_generic_page_diagnostics(
    tmp_path, monkeypatch, report, expected_ok, visible
):
    index = tmp_path / "index.html"
    index.write_text(COUNTER_HTML)
    context = ToolContext(root=tmp_path)

    async def measured_probe(_target, _keys):
        return report

    monkeypatch.setattr(play_probe, "probe_game", measured_probe)
    result = await run_play_probe({"target": "index.html"}, context)

    assert result.ok is expected_ok
    assert visible in result.output
    assert result.structured["game_probe"] == "not_applicable"
    diagnostics = result.structured["page_diagnostics"]
    assert diagnostics["console_error_count"] == len(report.console_errors)
    assert diagnostics["console_errors"] == list(report.console_errors)
    assert diagnostics["raf_per_second"] == report.raf_per_second
    assert diagnostics["resource_notes"] == list(report.ignored_resources)
    assert diagnostics["loaded_resources"] == list(report.asset_usage.loaded)
    assert not context.probed_games
    assert "kendiliğinden hareket" not in result.output


async def test_real_counter_mistaken_probe_does_not_add_game_findings_at_closure(tmp_path):
    pytest.importorskip("playwright.async_api")
    context = ToolContext(root=tmp_path)
    index = tmp_path / "index.html"
    context.changes.record(index)
    index.write_text(COUNTER_HTML)
    context.touched.add(index)

    # This is the actual short Chromium probe, not a scripted measurement.
    observation = await run_play_probe({"target": "index.html"}, context)

    assert observation.structured["game_probe"] == "not_applicable"
    assert observation.structured["page_diagnostics"]["console_error_count"] == 0
    assert not context.probed_games
    config = make_config(
        runtime={
            "web_verification": True,
            "browser_verification": True,
            "visual_verification": False,
        }
    )
    verifier = build_verifier(config, root=tmp_path, tool_context=context)
    assert verifier is not None
    result = await verifier.verify()

    assert result.ok, result.findings
    assert not any(e.criterion_id.startswith("game_probe:") for e in result.evidence)
    assert not any("düşman" in finding or "oyunda" in finding for finding in result.findings)


async def test_real_broken_counter_does_not_hide_javascript_failure_when_game_is_not_applicable(
    tmp_path,
):
    pytest.importorskip("playwright.async_api")
    context = ToolContext(root=tmp_path)
    (tmp_path / "index.html").write_text(COUNTER_HTML + "<script>updateCounter();</script>")

    observation = await run_play_probe({"target": "index.html"}, context)

    assert observation.ok is False
    assert observation.structured["game_probe"] == "not_applicable"
    assert "updateCounter is not defined" in observation.output
    assert observation.structured["page_diagnostics"]["console_error_count"] >= 1
    assert not context.probed_games
