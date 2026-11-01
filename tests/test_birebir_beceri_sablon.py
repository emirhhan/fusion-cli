"""Beceri şablonu ve dinamik bağlam: Claude Code ile birebir (#138, #168, #169, #171, #172,
#174, #177, #178, #180, #182, #183)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from fusion_cli.tools import frontmatter
from fusion_cli.tools.capabilities import Capability, CapabilityRegistry
from fusion_cli.tools.skill_commands import (
    TemplateEnv,
    build_invocation,
    discover_commands,
    render_template,
)
from fusion_cli.tools.skill_shell import (
    DISABLED_TEXT,
    SHELL_CONTEXT_TIMEOUT_S,
    ShellPolicy,
    SkillShellError,
    expand,
)


def _env(tmp_path: Path, effort: str = "") -> TemplateEnv:
    return TemplateEnv(tmp_path / "s", tmp_path, session_id="o-1", effort=effort)


def _skill(tmp_path: Path, text: str, **fields: object) -> Capability:
    path = tmp_path / "b" / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return Capability(name="b", description="", path=path, source="claude", **fields)  # type: ignore[arg-type]


# --- #138 / #171 / #172 / #169 ---------------------------------------------------- #


def test_konumsal_dolar_n_sifir_tabanli(tmp_path: Path) -> None:
    sonuc = render_template("ilk=$0 ikinci=$1 dizi=$ARGUMENTS[1] yok=$5", "a b", _env(tmp_path))

    assert sonuc == "ilk=a ikinci=b dizi=b yok="


def test_yer_tutucu_yoksa_arguments_etiketi(tmp_path: Path) -> None:
    sonuc = render_template("Kodu incele.", "src/app.py", _env(tmp_path))

    assert sonuc.endswith("\n\nARGUMENTS: src/app.py")


def test_claude_effort_degiskeni(tmp_path: Path) -> None:
    assert render_template("efor ${CLAUDE_EFFORT}", "", _env(tmp_path, "xhigh")) == "efor xhigh"


def test_adli_arguments_alani(tmp_path: Path) -> None:
    sonuc = render_template("#$issue -> $branch", "42 main", _env(tmp_path), names=("issue", "branch"))

    assert sonuc == "#42 -> main"


def test_arguments_ve_paths_frontmatter_okunur(tmp_path: Path) -> None:
    fields = frontmatter.parse_frontmatter(
        "---\nname: a\narguments: issue branch\npaths: src/*.{ts,tsx}, lib/**\nshell: powershell\n---\nx"
    )

    assert fields["arguments"] == ("issue", "branch")
    assert fields["paths"] == ("src/*.{ts,tsx}", "lib/**")
    assert fields["shell"] == "powershell"


def test_eski_fusion_degiskenleri_okunur_ve_uyarilir(tmp_path: Path) -> None:
    beceri = _skill(tmp_path, "---\nname: b\n---\ndizin ${FUSION_SKILL_DIR}", kind="komut")

    sonuc = build_invocation(beceri, "", _env(tmp_path), shell_allowed=False)

    assert str(tmp_path / "s") in sonuc.task
    assert any("${FUSION_SKILL_DIR} kullanımdan kalktı" in note for note in sonuc.notes)


# --- #168 ----------------------------------------------------------------------- #


def test_unlem_yalniz_satir_basinda_ya_da_bosluktan_sonra(tmp_path: Path) -> None:
    metin, _ = expand(
        "KEY=!`echo hayir`\nA !`echo evet`", cwd=tmp_path, policy=ShellPolicy(mode_allows=True)
    )

    assert "KEY=!`echo hayir`" in metin and "A evet" in metin


def test_cok_satirli_unlem_blogu(tmp_path: Path) -> None:
    metin, _ = expand(
        "Önce\n```!\necho bir\necho iki\n```\nSonra",
        cwd=tmp_path,
        policy=ShellPolicy(mode_allows=True),
    )

    assert metin == "Önce\nbir\niki\nSonra"


def test_basarisiz_komut_cagriyi_iptal_eder(tmp_path: Path) -> None:
    beceri = _skill(tmp_path, "---\nname: b\n---\nx !`false`")

    sonuc = build_invocation(beceri, "", _env(tmp_path), shell_allowed=True)

    assert sonuc.ok is False and sonuc.notes


def test_grep_bir_kodu_hata_sayilmaz(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("a\n", encoding="utf-8")

    metin, _ = expand("x !`grep zzz f.txt`", cwd=tmp_path, policy=ShellPolicy(mode_allows=True))

    assert metin == "x "


def test_izinsiz_kipte_komut_cagriyi_iptal_eder(tmp_path: Path) -> None:
    kanit = tmp_path / "kanit"
    with pytest.raises(SkillShellError, match="Shell command permission check failed"):
        expand(f"!`touch {kanit}`", cwd=tmp_path, policy=ShellPolicy(mode_allows=False))
    assert not kanit.exists()


def test_allowed_tools_bash_deseni_on_onaylar(tmp_path: Path) -> None:
    beceri = _skill(
        tmp_path, "---\nname: b\n---\nx !`echo tamam`", allowed_tools=("Bash(echo *)",)
    )

    sonuc = build_invocation(beceri, "", _env(tmp_path), shell_allowed=False)

    assert sonuc.ok and "x tamam" in sonuc.context


def test_deny_kurali_iptal_eder(tmp_path: Path) -> None:
    policy = ShellPolicy(mode_allows=True, rule_decision=lambda command: "deny")

    with pytest.raises(SkillShellError):
        expand("!`echo x`", cwd=tmp_path, policy=policy)


def test_disable_skill_shell_execution(tmp_path: Path) -> None:
    metin, _ = expand("!`echo x`", cwd=tmp_path, policy=ShellPolicy(disabled=True))

    assert metin == DISABLED_TEXT


def test_zaman_asimi_iki_dakika() -> None:
    assert SHELL_CONTEXT_TIMEOUT_S == 120.0


# --- #178 / #180 / #183 / #182 / #177 ------------------------------------------ #


def test_komut_dosyasinda_name_yok_sayilir(tmp_path: Path) -> None:
    home, root = tmp_path / "ev", tmp_path / "p"
    (root / ".claude" / "commands").mkdir(parents=True)
    (root / ".claude" / "commands" / "deploy.md").write_text(
        "---\nname: baska\n---\nx", encoding="utf-8"
    )

    assert [c.name for c in discover_commands(home, root)] == ["deploy"]  # type: ignore[attr-defined]


def test_skill_md_aciklamasi_yoksa_ilk_satir(tmp_path: Path) -> None:
    home, root = tmp_path / "ev", tmp_path / "p"
    (home / ".claude" / "skills" / "x").mkdir(parents=True)
    (home / ".claude" / "skills" / "x" / "SKILL.md").write_text(
        "---\nname: x\n---\n\n# Sürüm notu yazar\nDetay", encoding="utf-8"
    )
    root.mkdir()

    beceri = CapabilityRegistry(home, root).get_skill("x")

    assert beceri is not None and beceri.description == "Sürüm notu yazar"


def test_fusion_commands_koku_kullanimdan_kalkti_uyarisi(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    home, root = tmp_path / "ev", tmp_path / "p"
    (root / ".fusion" / "commands").mkdir(parents=True)
    (root / ".fusion" / "commands" / "eski.md").write_text("x", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        names = [c.name for c in discover_commands(home, root)]  # type: ignore[attr-defined]

    assert names == ["eski"]
    assert any("kullanımdan kalktı" in record.getMessage() for record in caplog.records)


def test_turkce_frontmatter_takma_adi_bir_kez_uyarilir(caplog: pytest.LogCaptureFixture) -> None:
    frontmatter._WARNED_KEYS.discard("efor")
    with caplog.at_level(logging.WARNING):
        frontmatter.parse_frontmatter("---\nefor: high\n---\nx")
        frontmatter.parse_frontmatter("---\nefor: high\n---\nx")

    uyarilar = [r for r in caplog.records if "'efor' kullanımdan kalktı" in r.getMessage()]
    assert len(uyarilar) == 1


def test_disable_model_invocation_alt_ajana_on_yuklenmez(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from fusion_cli.engines.agent import team_settings

    gizli = _skill(tmp_path, "---\nname: b\n---\nGizli", model_invocable=False)
    library = SimpleNamespace(get_skill=lambda name: gizli)
    deps = SimpleNamespace(capabilities=library)
    persona = SimpleNamespace(skills=("b",), name="ajan")

    assert team_settings.preloaded_skills(deps, persona) == ""  # type: ignore[arg-type]
