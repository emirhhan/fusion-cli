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


def test_diff_git_ozeti_ve_oturum_turlari(tmp_path):
    """Claude Code `/diff` (#230): çalışma ağacı farkı + bu oturumun düzenlemeleri tur tur."""
    import subprocess

    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.memory.factory import null_memory

    from .fakes import make_config

    root = tmp_path / "proje"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    dosya = root / "a.txt"
    dosya.write_text("bir\n")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "i"],
        check=True,
    )
    state = ReplState(
        config=make_config(memory_dir=tmp_path / "m"),
        memory=null_memory(),
        root=root,
        home=tmp_path / "ev",
    )
    checkpoint = state.checkpoints.begin("a.txt'yi güncelle", [])
    checkpoint.changes.record(dosya)
    dosya.write_text("iki\n")
    komut = build_registry().get("diff")
    assert komut is not None
    cikti = komut.handler(state, "tam")
    assert "a.txt" in cikti and "+iki" in cikti
    assert "Tur 1: a.txt'yi güncelle" in cikti
