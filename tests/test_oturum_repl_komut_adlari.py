"""Claude Code komut adları ve takma adları (oturum-repl alanı, tur 2)."""

from __future__ import annotations

from fusion_cli.cli.repl.commands import RENDERED_COMMANDS, build_registry


def test_cost_ve_stats_usage_takma_adi():
    """Claude Code: `/cost` ve `/stats` `/usage` takma adıdır (#208)."""
    registry = build_registry()
    usage = registry.get("usage")
    assert usage is not None
    assert registry.get("cost") is usage and registry.get("stats") is usage
    # Model performans tablosu ayrı ada taşındı; Bellek grubunda kalır.
    perf = registry.get("model-stats")
    assert perf is not None and perf.group == "Bellek"
    assert "model-stats" in RENDERED_COMMANDS


def test_continue_resume_takma_adi():
    """Claude Code: `/resume` takma adı `/continue` (#203)."""
    registry = build_registry()
    assert registry.get("continue") is registry.get("resume")
