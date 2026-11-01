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


def test_ayni_adda_ikisi_de_kalir_ic_ice_dizin_nitelikli(tmp_path: Path):
    """Claude Code (#158): `/ortak` kök beceri, `/paket:ortak` iç içe beceri."""
    kok = tmp_path
    _skill(kok / ".claude" / "skills", "ortak", description="kökteki")
    _skill(kok / "paket" / ".claude" / "skills", "ortak", description="paketteki")
    (kok / "paket" / "a.py").write_text("", "utf-8")
    registry = CapabilityRegistry(tmp_path / "ev", kok)

    note = discover_nested_skills(registry, kok, (kok / "paket" / "a.py",))
    assert note is not None and "paket:ortak" in note.content
    assert registry.get_skill("ortak").description == "kökteki"  # type: ignore[union-attr]
    nested = registry.get_skill("paket:ortak")
    assert nested is not None and "paket/" in nested.description and "paketteki" in nested.description


def test_ust_dizin_becerileri_depo_kokune_kadar_yuklenir(tmp_path: Path):
    """Claude Code (#158): `packages/frontend`'de başlasa da kökün becerileri gelir."""
    depo = tmp_path / "depo"
    (depo / ".git").mkdir(parents=True)
    _skill(depo / ".claude" / "skills", "kok-becerisi", description="kök")
    _skill(tmp_path / ".claude" / "skills", "depo-disi", description="dış")
    baslangic = depo / "packages" / "frontend"
    baslangic.mkdir(parents=True)

    registry = CapabilityRegistry(tmp_path / "ev", baslangic)

    assert registry.get_skill("kok-becerisi") is not None
    assert registry.get_skill("depo-disi") is None


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


async def test_masaustu_katalogu_kesfedilenleri_gosterir_yenileme_korur(tmp_path: Path):
    """Ölçüldü (31 Ekim): masaüstü katalog defteri (`_all_capabilities`) tembel keşfedilen
    becerileri göstermiyordu; `_refresh_capabilities` defteri yeniden kurunca keşif kayboluyordu."""
    from fusion_cli.appserver.protocol import Request
    from fusion_cli.appserver.session import AppSession

    from .test_appserver_session import _sonuc

    kok = _monorepo(tmp_path / "depo")
    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=kok, home=tmp_path / "ev")
    assert oturum._state.capabilities is not None
    discover_nested_skills(oturum._state.capabilities, kok, (kok / "paket" / "alt" / "kod.py",))

    oturum._refresh_capabilities()
    await oturum.handle(Request(id="1", name="yetenek.katalog", data={}))

    assert oturum._state.capabilities.get_skill("paket-becerisi") is not None
    adlar = {item["ad"] for item in _sonuc(satirlar, "1")["beceriler"]}
    assert {"paket-becerisi", "alt-becerisi"} <= adlar
    await oturum.close()


def test_config_ile_yeniden_kurulan_defter_kesfi_korur(tmp_path: Path):
    from fusion_cli.cli.repl.config_command import config_command
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.config.loader import load_config
    from fusion_cli.memory.factory import null_memory

    kok = _monorepo(tmp_path / "depo")
    source = tmp_path / "config.yaml"
    source.write_text("runtime: {}\n", encoding="utf-8")
    state = ReplState(
        config=load_config(source), memory=null_memory(), root=kok, home=tmp_path / "ev"
    )
    discover_nested_skills(state.capabilities, kok, (kok / "paket" / "alt" / "kod.py",))

    config_command(state, "capabilities.disabled=yok")

    assert state.capabilities is not None
    assert state.capabilities.get_skill("paket-becerisi") is not None
