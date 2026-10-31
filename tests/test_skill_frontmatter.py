"""SKILL.md frontmatter zenginliği ve komut şablonlama (P-019, P-020).

Ölçüldü (31 Ekim): parse_frontmatter yalnız name/description/tools okuyordu; allowed-tools,
model, effort, context, disable-model-invocation, argument-hint yok sayılıyordu; $ARGUMENTS
şablonu ve !`cmd` dinamik bağlam yoktu; .claude/commands/*.md hiç taranmıyordu.
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.tools.capabilities import Capability, CapabilityRegistry, parse_frontmatter
from fusion_cli.tools.skill_commands import (
    MAX_SHELL_OUTPUT_CHARS,
    TemplateEnv,
    build_invocation,
    discover_commands,
    expand_shell_context,
    render_template,
)

ZENGIN = """---
name: deploy
description: Üretime çıkar
when_to_use: Kullanıcı "yayınla" dediğinde
argument-hint: "[ortam]"
allowed-tools: Bash(git *), Read
model: anthropic/claude-sonnet
effort: high
context: fork
disable-model-invocation: true
user-invocable: true
---
Gövde
"""


def test_zengin_frontmatter_alanlari_okunur():
    fields = parse_frontmatter(ZENGIN)

    assert fields["allowed_tools"] == ("Bash(git *)", "Read")
    assert fields["model"] == "anthropic/claude-sonnet"
    assert fields["effort"] == "high"
    assert fields["context"] == "fork"
    assert fields["model_invocable"] is False
    assert fields["user_invocable"] is True
    assert fields["argument_hint"] == "[ortam]"
    assert "yayınla" in str(fields["when_to_use"])


def test_turkce_anahtarlar_da_kabul_edilir():
    fields = parse_frontmatter(
        "---\nname: a\nizinli-araclar: [Read]\nmodel-cagirmasin: evet\n"
        "arguman-ipucu: <dosya>\n---\nx"
    )

    assert fields["allowed_tools"] == ("Read",)
    assert fields["model_invocable"] is False
    assert fields["argument_hint"] == "<dosya>"


def test_capability_frontmatter_alanlarini_tasir(tmp_path: Path):
    home, root = tmp_path / "ev", tmp_path / "proje"
    (home / ".claude" / "skills" / "deploy").mkdir(parents=True)
    (home / ".claude" / "skills" / "deploy" / "SKILL.md").write_text(ZENGIN, encoding="utf-8")
    root.mkdir()

    skill = CapabilityRegistry(home, root).get_skill("deploy")

    assert skill is not None
    assert skill.kind == "beceri"
    assert skill.model_invocable is False
    assert skill.allowed_tools == ("Bash(git *)", "Read")
    assert skill.context == "fork"
    assert skill.argument_hint == "[ortam]"


# --- Şablon ------------------------------------------------------------------- #


def _env(tmp_path: Path) -> TemplateEnv:
    return TemplateEnv(skill_dir=tmp_path / "s", project_dir=tmp_path, session_id="oturum-1")


def test_arguments_ve_konumsal_degiskenler(tmp_path: Path):
    metin = "Hepsi: $ARGUMENTS | ilk: $1 | ikinci: $2 | sıfır: $ARGUMENTS[0] | yok: $9"

    assert render_template(metin, "a b", _env(tmp_path)) == (
        "Hepsi: a b | ilk: a | ikinci: b | sıfır: a | yok: "
    )


def test_ortam_degiskenleri_ve_kacis(tmp_path: Path):
    metin = "dizin ${FUSION_SKILL_DIR} ${CLAUDE_PROJECT_DIR} ${CLAUDE_SESSION_ID} fiyat \\$5"

    sonuc = render_template(metin, "", _env(tmp_path))

    assert str(tmp_path / "s") in sonuc
    assert str(tmp_path) in sonuc
    assert "oturum-1" in sonuc
    assert sonuc.endswith("fiyat $5")


def test_yer_tutucu_yoksa_arguman_sona_eklenir(tmp_path: Path):
    sonuc = render_template("Kodu incele.", "src/app.py", _env(tmp_path))

    assert sonuc.startswith("Kodu incele.")
    assert sonuc.rstrip().endswith("src/app.py")


# --- !`cmd` dinamik bağlam ----------------------------------------------------- #


def test_shell_baglami_izinliyse_calisir_ve_sinirlanir(tmp_path: Path):
    metin = "Durum: !`echo merhaba`\nUzun: !`python3 -c \"print('x'*5000)\"`"

    sonuc, notlar = expand_shell_context(metin, cwd=tmp_path, allowed=True)

    assert "Durum: merhaba" in sonuc
    assert sonuc.count("x") <= MAX_SHELL_OUTPUT_CHARS + 10
    assert any("kırpıldı" in n for n in notlar)


def test_shell_baglami_izinsizse_calismaz_ve_notta_gorunur(tmp_path: Path):
    kanit = tmp_path / "kanit"
    metin = f"!`touch {kanit}`"

    sonuc, notlar = expand_shell_context(metin, cwd=tmp_path, allowed=False)

    assert not kanit.exists()
    assert "[komut çalıştırılmadı" in sonuc
    assert notlar


# --- .claude/commands keşfi ---------------------------------------------------- #


def test_komut_dosyalari_kesfedilir_ic_ice_ad_iki_nokta_ile(tmp_path: Path):
    home, root = tmp_path / "ev", tmp_path / "proje"
    (home / ".claude" / "commands").mkdir(parents=True)
    (home / ".claude" / "commands" / "deploy.md").write_text(
        "---\ndescription: Üretime çıkar\n---\nDeploy et: $ARGUMENTS", encoding="utf-8"
    )
    (root / ".claude" / "commands" / "frontend").mkdir(parents=True)
    (root / ".claude" / "commands" / "frontend" / "component.md").write_text(
        "Bileşen oluştur", encoding="utf-8"
    )

    komutlar = {c.name: c for c in discover_commands(home, root)}

    assert komutlar["deploy"].kind == "komut"
    assert komutlar["deploy"].description == "Üretime çıkar"
    assert komutlar["deploy"].source == "claude"
    assert komutlar["frontend:component"].source == "proje"
    assert komutlar["frontend:component"].description == "Bileşen oluştur"
    # Komutlar beceri kataloğunda görünür ve `/ad` ile çağrılabilir.
    assert CapabilityRegistry(home, root).get_skill("frontend:component") is not None


def test_invocation_komut_icin_gorev_beceri_icin_baglam_uretir(tmp_path: Path):
    komut = Capability(
        name="deploy", description="", path=tmp_path / "deploy.md", source="claude", kind="komut"
    )
    komut.path.write_text("Deploy et: $ARGUMENTS", encoding="utf-8")
    beceri_yol = tmp_path / "rapor" / "SKILL.md"
    beceri_yol.parent.mkdir()
    beceri_yol.write_text(
        "---\nname: rapor\nallowed-tools: Read, Grep\ncontext: fork\n---\nRapor yaz: $1",
        encoding="utf-8",
    )
    beceri = Capability(
        name="rapor",
        description="",
        path=beceri_yol,
        source="proje",
        allowed_tools=("Read", "Grep"),
        context="fork",
    )
    env = _env(tmp_path)

    k = build_invocation(komut, "staging", env, shell_allowed=False)
    b = build_invocation(beceri, "ekim", env, shell_allowed=False)

    assert k.task == "Deploy et: staging" and k.context == ""
    assert b.task == "ekim"
    assert '<beceri ad="rapor"' in b.context and "Rapor yaz: ekim" in b.context
    assert "allowed-tools" not in b.context  # ön madde modele gitmez
    assert b.allowed_tools == {"read_file", "view_file", "grep_search", "search_code"}
    assert b.fork is True
    bos = build_invocation(beceri, "", env, shell_allowed=False)
    assert "rapor" in bos.task  # varsayılan görev metni beceri adını taşır


# --- İnceleme bulguları (31 Ekim) --------------------------------------------- #


def test_shell_baglami_riskli_komutu_izinli_olsa_da_calistirmaz(tmp_path: Path):
    """Ölçüldü: `!`git push --force`` izinli kökte run_shell tehlike denetimi olmadan koşuyordu."""
    metin, notlar = expand_shell_context(
        "A: !`git push --force origin HEAD`\nB: !`sudo ls`\nC: !`echo canli`",
        cwd=tmp_path,
        allowed=True,
    )

    assert "[komut çalıştırılmadı" in metin and "canli" in metin
    assert "force push" not in metin
    assert any("riskli" in not_ and "git push" in not_ for not_ in notlar)
    assert any("sudo" in not_ for not_ in notlar)


def test_shell_baglami_salt_okur_kipinde_yazan_komut_calismaz(tmp_path: Path):
    metin, notlar = expand_shell_context(
        "X: !`touch sizinti` Y: !`ls`", cwd=tmp_path, allowed=True, read_only=True
    )

    assert not (tmp_path / "sizinti").exists()
    assert "[komut çalıştırılmadı: touch sizinti]" in metin
    assert any("salt-okur" in not_ for not_ in notlar)


def test_allowed_tools_bosluk_ayrimli_ve_parantezli_yazim():
    """Agent Skills standardı boşlukla ayırır; `Bash(git add:*, git commit:*)` iç virgül taşır."""
    assert parse_frontmatter("---\nallowed-tools: Read Grep\n---\nx")["allowed_tools"] == (
        "Read",
        "Grep",
    )
    assert parse_frontmatter("---\nallowed-tools: Bash(git add:*, git commit:*) Read\n---\nx")[
        "allowed_tools"
    ] == ("Bash(git add:*, git commit:*)", "Read")
    assert parse_frontmatter("---\nallowed-tools: Read, Grep\n---\nx")["allowed_tools"] == (
        "Read",
        "Grep",
    )


def test_eslenmeyen_allowed_tools_kisit_uygulamaz_ve_not_duser(tmp_path: Path):
    """Ölçüldü: yalnız `TodoWrite` yazılmışsa `map_tools` boş küme veriyor, tur araçsızdı."""
    from fusion_cli.tools.capabilities import CapabilityRegistry

    folder = tmp_path / "ev" / ".claude" / "skills" / "plan"
    folder.mkdir(parents=True)
    folder.joinpath("SKILL.md").write_text(
        "---\nname: plan\nallowed-tools: TodoWrite Skill\n---\nPlanla", encoding="utf-8"
    )
    skill = CapabilityRegistry(tmp_path / "ev", tmp_path / "proje").get_skill("plan")
    assert skill is not None

    cagri = build_invocation(
        skill, "", TemplateEnv(skill.path.parent, tmp_path / "proje"), shell_allowed=False
    )

    assert cagri.allowed_tools is None
    assert any("TodoWrite" in not_ and "kısıt" in not_ for not_ in cagri.notes)
