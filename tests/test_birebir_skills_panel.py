"""`/skills` paneli görünürlüğü döndürür ve `skillOverrides`'a yazar (Claude Code #176)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.cli.repl import skills_panel
from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.loader import load_config
from fusion_cli.config.models import SkillVisibility
from fusion_cli.config.skill_overrides_writer import next_visibility, write_skill_overrides
from fusion_cli.memory.factory import null_memory
from fusion_cli.tools.capabilities import CapabilityRegistry


def _skill(home: Path, name: str) -> None:
    folder = home / ".claude" / "skills" / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} açıklaması\n---\ngövde", encoding="utf-8"
    )


@pytest.fixture
def state(tmp_path: Path) -> ReplState:
    home, root = tmp_path / "ev", tmp_path / "proje"
    root.mkdir()
    _skill(home, "alfa")
    _skill(home, "beta")
    source = tmp_path / "config.yaml"
    source.write_text("", encoding="utf-8")
    repl = ReplState(config=load_config(source), memory=null_memory(), root=root, home=home)
    repl.capabilities = CapabilityRegistry(home, root)
    return repl


def _local(state: ReplState) -> dict[str, object]:
    return json.loads((state.root / ".claude" / "settings.local.json").read_text("utf-8"))


def test_dongu_sirasi() -> None:
    assert next_visibility(SkillVisibility.ON) is SkillVisibility.NAME_ONLY
    assert next_visibility(SkillVisibility.OFF) is SkillVisibility.ON


def test_yazici_diger_anahtarlari_korur(tmp_path: Path) -> None:
    root = tmp_path / "proje"
    (root / ".claude").mkdir(parents=True)
    (root / ".claude" / "settings.local.json").write_text(
        '{"permissions": {"allow": ["Bash(ls)"]}, "skillOverrides": {"x": "off"}}', "utf-8"
    )

    write_skill_overrides(root, {"y": SkillVisibility.NAME_ONLY})

    data = json.loads((root / ".claude" / "settings.local.json").read_text("utf-8"))
    assert data["permissions"] == {"allow": ["Bash(ls)"]}
    assert data["skillOverrides"] == {"x": "off", "y": "name-only"}


def test_terminal_numarali_liste_ve_n_ile_dongu(state: ReplState) -> None:
    skills = build_registry(state.home).get("skills")
    assert skills is not None

    liste = skills.handler(state, "")
    assert "1. alfa" in liste and "· on ·" in liste and "/skills <n>" in liste

    cikti = skills.handler(state, "1")
    assert "alfa: name-only" in cikti
    assert _local(state)["skillOverrides"] == {"alfa": "name-only"}
    # Katalog yeni görünürlükle kuruldu: dizinde yalnız ad.
    alfa = next(s for s in state.capabilities.skills() if s.name == "alfa")  # type: ignore[union-attr]
    assert alfa.describe_in_index is False
    assert "Geçersiz" in skills.handler(state, "9")


async def test_tui_paneli_enter_dondurur_esc_kaydeder_off_listede_kalir(state: ReplState) -> None:
    secimler = iter(["beta", "beta", "beta", None])

    async def await_choice(title: str, choices: list, **_options: object) -> str | None:
        assert "Esc" in title and {c.value for c in choices} == {"alfa", "beta"}
        return next(secimler)

    cikti = await skills_panel.run_tui_panel(state, await_choice)

    assert "beta: off" in cikti
    assert _local(state)["skillOverrides"] == {"beta": "off"}
    assert "beta" not in {s.name for s in state.capabilities.skills()}  # type: ignore[union-attr]
    # Kapalı beceri panelde yine görünür (yeniden açılabilsin).
    assert {item.name for item, _ in skills_panel.panel_items(state)} == {"alfa", "beta"}


async def test_masaustu_gorunurluk_rpc(tmp_path: Path) -> None:
    from fusion_cli.appserver.protocol import Request
    from fusion_cli.appserver.session import AppSession

    home, root = tmp_path / "home", tmp_path / "project"
    root.mkdir()
    _skill(home, "review")
    lines: list[str] = []
    session = AppSession(lines.append, root=root, home=home)

    await session.handle(
        Request(id="g", name="yetenek.gorunurluk", data={"ad": "review", "gorunurluk": "off"})
    )
    sonuc = json.loads(lines[-1])["veri"]
    await session.handle(Request(id="h", name="yetenek.gorunurluk", data={"ad": "yok"}))
    hata = json.loads(lines[-1])["veri"]
    await session.close()

    assert sonuc["ok"] is True and sonuc["gorunurluk"] == "off"
    data = json.loads((root / ".claude" / "settings.local.json").read_text("utf-8"))
    assert data["skillOverrides"] == {"review": "off"}
    assert hata["ok"] is False


def _buyuk(state: ReplState) -> None:
    folder = state.home / ".claude" / "skills" / "gamma"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        "---\nname: gamma\ndescription: " + "uzun açıklama " * 30 + "\n---\ngövde", "utf-8"
    )
    state.capabilities = CapabilityRegistry(state.home, state.root)


def test_terminal_t_ile_token_siralamasi_ve_metinle_filtre(state: ReplState) -> None:
    """#176: `/skills t` liste maliyetine göre sıralar; `/skills <metin>` paneli süzer."""
    _buyuk(state)
    skills = build_registry(state.home).get("skills")
    assert skills is not None

    sirali = skills.handler(state, "t").splitlines()
    assert "gamma" in sirali[0]
    suzulmus = skills.handler(state, "bet")
    assert "beta" in suzulmus and "alfa" not in suzulmus
    # Numara tam listedeki sırayı korur: `/skills <n>` aynı beceriyi döndürür.
    numara = suzulmus.split(".", 1)[0].strip()
    assert "beta: name-only" in skills.handler(state, numara)


async def test_tui_paneli_t_tusu_siralar_ve_filtreyi_acar(state: ReplState) -> None:
    _buyuk(state)
    seen: list[list[str]] = []
    secimler = iter([skills_panel.SORT_TOKENS, None])

    async def await_choice(title: str, choices: list, **options: object) -> str | None:
        assert options.get("filterable") is True
        assert options.get("hotkeys") == {"t": skills_panel.SORT_TOKENS}
        seen.append([c.value for c in choices])
        return next(secimler)

    await skills_panel.run_tui_panel(state, await_choice)

    assert seen[0][0] == "alfa" and seen[1][0] == "gamma"


def test_guvenilen_izin_dosyasina_yazinca_guven_karmasi_tazelenir(tmp_path: Path) -> None:
    """#176: Fusion'ın kendi yazımı güvenilen dosyayı güvenilmez yapmaz; güvenilmeyeni güvenmez."""
    from fusion_cli.config import trust

    root = tmp_path / "proje"
    (root / ".claude").mkdir(parents=True)
    (root / ".claude" / "settings.local.json").write_text('{"permissions": {}}', "utf-8")
    trust.record_permissions_digest(root)
    assert trust.is_permissions_trusted(root)

    write_skill_overrides(root, {"x": SkillVisibility.OFF})
    assert trust.is_permissions_trusted(root)

    other = tmp_path / "baska"
    (other / ".claude").mkdir(parents=True)
    (other / ".claude" / "settings.local.json").write_text('{"permissions": {}}', "utf-8")
    write_skill_overrides(other, {"x": SkillVisibility.OFF})
    assert not trust.is_permissions_trusted(other)


async def test_tui_paneli_space_ile_doner_imleci_ve_suzgeci_korur(state: ReplState) -> None:
    """Belge (/skills): Space görünürlüğü döndürür; döngüden sonra imleç aynı beceride kalır."""
    gorulen: list[dict[str, object]] = []
    secimler = iter(["beta", None])

    async def await_choice(title: str, choices: list, **options: object) -> str | None:
        gorulen.append(options)
        return next(secimler)

    await skills_panel.run_tui_panel(state, await_choice)

    assert gorulen[0].get("space_selects") is True
    assert gorulen[0].get("initial") is None and gorulen[0].get("keep_filter") is False
    assert gorulen[1].get("initial") == "beta" and gorulen[1].get("keep_filter") is True


async def test_tui_modalinda_space_secer_ve_suzgec_imlec_korunur() -> None:
    import asyncio

    from fusion_cli.ui.picker import Choice

    from .test_tui import _tui

    tui, _ = _tui()
    secenekler = [Choice("alfa", "alfa"), Choice("beta", "beta"), Choice("bet2", "bet2")]
    ilk = asyncio.ensure_future(
        tui.await_choice("b", secenekler, filterable=True, space_selects=True)
    )
    await asyncio.sleep(0)
    for harf in "bet":
        tui._choice_key(harf)
    tui._move_choice(1)
    tui._choice_key(" ")
    assert await ilk == "bet2"

    ikinci = asyncio.ensure_future(
        tui.await_choice(
            "b", secenekler, filterable=True, space_selects=True, initial="bet2", keep_filter=True
        )
    )
    await asyncio.sleep(0)
    assert [c.value for c in tui._choices] == ["beta", "bet2"]
    assert tui._choices[tui._choice_index].value == "bet2"
    tui._resolve(None)
    assert await ikinci is None


async def test_masaustu_gorunurluk_listesi_rpc_kapalilari_da_listeler(tmp_path: Path) -> None:
    """Masaüstü `/skills` liste paneli: tüm beceriler ham görünürlük ve maliyetle, ada göre."""
    from fusion_cli.appserver.protocol import Request
    from fusion_cli.appserver.session import AppSession

    home, root = tmp_path / "home", tmp_path / "project"
    root.mkdir()
    _skill(home, "zeta")
    _skill(home, "alfa")
    write_skill_overrides(root, {"zeta": SkillVisibility.OFF})
    lines: list[str] = []
    session = AppSession(lines.append, root=root, home=home)

    await session.handle(Request(id="l", name="yetenek.gorunurluk_listesi", data={}))
    sonuc = json.loads(lines[-1])["veri"]
    await session.close()

    assert sonuc["ok"] is True
    satirlar = sonuc["beceriler"]
    assert [s["ad"] for s in satirlar] == ["alfa", "zeta"]
    assert satirlar[1]["gorunurluk"] == "off" and satirlar[0]["gorunurluk"] == "on"
    assert satirlar[0]["belirtec"] > 0 and satirlar[0]["aciklama"] == "alfa açıklaması"
