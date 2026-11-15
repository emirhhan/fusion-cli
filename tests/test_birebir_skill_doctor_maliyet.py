"""`/skill-doctor`: beceri başına bağlam maliyeti ve kullanım sıklığı (Claude Code #177)."""

from __future__ import annotations

from pathlib import Path

from fusion_cli.engines.agent import skill_usage
from fusion_cli.engines.agent.skill_cost_report import render_cost_report, skill_costs
from fusion_cli.tools.capabilities import CapabilityRegistry


def _skill(home: Path, name: str, extra: str = "", body: str = "gövde") -> None:
    folder = home / ".claude" / "skills" / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} açıklaması uzun uzun\n{extra}---\n{body}",
        encoding="utf-8",
    )


def test_maliyet_ve_kullanim_raporu(tmp_path: Path) -> None:
    home, root, bellek = tmp_path / "ev", tmp_path / "proje", tmp_path / "bellek"
    root.mkdir()
    _skill(home, "buyuk", body="x" * 4_000)
    _skill(home, "gizli", "disable-model-invocation: true\n")
    _skill(home, "sik")
    for _ in range(3):
        skill_usage.record_invocation(bellek, "sik")
    registry = CapabilityRegistry(home, root)

    costs = {c.name: c for c in skill_costs(registry, bellek)}
    rapor = render_cost_report(tuple(skill_costs(registry, bellek)))

    assert costs["sik"].uses == 3 and costs["buyuk"].uses == 0
    assert costs["buyuk"].body_tokens > costs["sik"].body_tokens
    # Modelin çağıramadığı beceri listede yer kaplamaz.
    assert costs["gizli"].listing_tokens == 0 and costs["sik"].listing_tokens > 0
    assert "3 çağrı" in rapor and "listede yok" in rapor
    assert "skillOverrides" in rapor and "buyuk" in rapor.split("Hiç çağrılmamış")[1]


def test_skill_doctor_komutu_maliyet_ve_teshisi_birlikte_verir(tmp_path: Path) -> None:
    from fusion_cli.cli.repl.commands import build_registry
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.config.loader import load_config
    from fusion_cli.memory.factory import null_memory

    home, root = tmp_path / "ev", tmp_path / "proje"
    root.mkdir()
    _skill(home, "tek")
    source = tmp_path / "config.yaml"
    source.write_text("", encoding="utf-8")
    state = ReplState(config=load_config(source), memory=null_memory(), root=root, home=home)
    state.capabilities = CapabilityRegistry(home, root)

    cikti = build_registry(home).get("skill-doctor").handler(state, "")  # type: ignore[union-attr]

    assert "Beceri maliyeti" in cikti and "· tek [" in cikti
    assert "Beceri teşhisi" in cikti


def test_govde_maliyeti_frontmatter_haric_karakterle(tmp_path: Path) -> None:
    """#177: gövde maliyeti bayt değil karakter; frontmatter sayılmaz (Türkçe çok baytlı)."""
    home, root = tmp_path / "ev", tmp_path / "proje"
    root.mkdir()
    _skill(home, "turkce", extra="metadata: " + "m" * 2_000 + "\n", body="ğ" * 4_000)

    cost = next(c for c in skill_costs(CapabilityRegistry(home, root), None) if c.name == "turkce")

    from fusion_cli.engines.agent.context_budget import CHARS_PER_TOKEN_ESTIMATE as PER

    # 4.000 karakter; bayt (8.000) ya da frontmatter (~2.000) sayılmaz.
    assert cost.body_tokens == (4_000 + PER - 1) // PER


def test_esanli_cagri_sayaci_sayi_kaybetmez(tmp_path: Path) -> None:
    """#177: iki oturum aynı anda sayarsa biri ötekinin sayısını ezmez."""
    import threading

    bellek = tmp_path / "bellek"
    threads = [
        threading.Thread(target=skill_usage.record_invocation, args=(bellek, "ortak"))
        for _ in range(24)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert skill_usage.load_counts(bellek)["ortak"] == 24
