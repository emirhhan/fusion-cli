"""Monorepo alt klasörlerindeki `.claude/skills` becerilerinin tembel keşfi (P-052).

Ölçüldü (31 Ekim): yalnız proje kökünün `.claude/skills` dizini taranıyordu; `paket/` alt
paketindeki `paket/.claude/skills/x/SKILL.md` model o pakette çalışırken de görünmüyordu
(Claude Code iç içe dizinlerdeki becerileri yükler).
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.engines.agent.loop import run_agent
from fusion_cli.engines.agent.nested_skills import discover_nested_skills, nested_skill_dirs
from fusion_cli.tools.capabilities import CapabilityRegistry

from .fakes import RecordingSink, ScriptedProvider, model_result, tool_call
from .test_agent_loop import _deps, _kur


def _skill(folder: Path, name: str, description: str = "paket becerisi") -> None:
    (folder / name).mkdir(parents=True, exist_ok=True)
    (folder / name / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\nGövde", encoding="utf-8"
    )


def _monorepo(kok: Path) -> Path:
    _skill(kok / ".claude" / "skills", "kok-becerisi")
    _skill(kok / "paket" / ".claude" / "skills", "paket-becerisi")
    _skill(kok / "paket" / "alt" / ".agents" / "skills", "alt-becerisi")
    _skill(kok / "node_modules" / "x" / ".claude" / "skills", "gurultu")
    (kok / "paket" / "alt").mkdir(parents=True, exist_ok=True)
    (kok / "paket" / "alt" / "kod.py").write_text("x = 1\n", "utf-8")
    (kok / "node_modules" / "x" / "i.js").write_text("", "utf-8")
    return kok


def test_alt_klasor_beceri_dizinleri_icten_disa_kok_haric(tmp_path: Path):
    kok = _monorepo(tmp_path)

    found = nested_skill_dirs(kok, kok / "paket" / "alt" / "kod.py")

    assert found == (
        kok / "paket" / "alt" / ".agents" / "skills",
        kok / "paket" / ".claude" / "skills",
    )
    assert nested_skill_dirs(kok, kok / "node_modules" / "x" / "i.js") == ()
    assert nested_skill_dirs(kok, tmp_path.parent / "disari.py") == ()


def test_erisim_sonrasi_katalog_buyur_ve_duyuru_bir_kez_duser(tmp_path: Path):
    kok = _monorepo(tmp_path)
    registry = CapabilityRegistry(tmp_path / "ev", kok)
    assert registry.get_skill("paket-becerisi") is None

    note = discover_nested_skills(registry, kok, (kok / "paket" / "alt" / "kod.py",))
    again = discover_nested_skills(registry, kok, (kok / "paket" / "alt" / "kod.py",))

    assert note is not None and note.harness_note
    assert "paket-becerisi (paket/.claude/skills/paket-becerisi)" in note.content
    assert "alt-becerisi" in note.content and "kok-becerisi" not in note.content
    assert again is None
    item = registry.get_skill("paket-becerisi")
    assert item is not None and item.source == "proje"
    # `/add-dir` sonrası yeni defter keşfedilen dizinleri unutmaz.
    assert registry.with_extra_roots(()).get_skill("alt-becerisi") is not None


def test_ayni_adda_kok_becerisi_kazanir(tmp_path: Path):
    kok = tmp_path
    _skill(kok / ".claude" / "skills", "ortak", description="kökteki")
    _skill(kok / "paket" / ".claude" / "skills", "ortak", description="paketteki")
    (kok / "paket" / "a.py").write_text("", "utf-8")
    registry = CapabilityRegistry(tmp_path / "ev", kok)

    assert discover_nested_skills(registry, kok, (kok / "paket" / "a.py",)) is None
    assert registry.get_skill("ortak").description == "kökteki"  # type: ignore[union-attr]


async def test_dongu_alt_paket_okumasindan_sonra_beceriyi_duyurur(monkeypatch, tmp_path: Path):
    kok = _monorepo(tmp_path)
    saglayici = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("read_file", path="paket/alt/kod.py")]),
                model_result("bitti"),
            ]
        ),
    )
    deps = _deps(kok, RecordingSink())
    deps.capabilities = CapabilityRegistry(tmp_path / "ev", kok)

    await run_agent("paket/alt/kod.py dosyasını oku", deps)

    ikinci = " ".join(m.content for m in saglayici.seen_messages[1])
    assert "paket-becerisi" in ikinci and "read_skill" in ikinci
    assert deps.capabilities.get_skill("paket-becerisi") is not None
