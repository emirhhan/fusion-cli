"""`.claude/rules/` kural dosyaları: `paths:` ile yol kapsamı, kullanıcı kuralları (P-016).

Ölçüldü (31 Ekim): `.claude/rules` hiç taranmıyordu; Claude Code bu dosyaları özyinelemeli
yükler, `paths:` frontmatter'ı olanları yalnız eşleşen dosyaya dokunulduğunda devreye alır.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.engines.agent.instruction_rules import (
    MAX_RULES_CHARS,
    discover_rules,
    matches_paths,
    scoped_rules_for,
    unscoped_rules_block,
)
from fusion_cli.engines.agent.project_instructions import (
    load_nested_instructions,
    read_all_instructions,
)


@pytest.fixture
def proje(tmp_path: Path) -> Path:
    root = tmp_path / "proje"
    (root / ".claude" / "rules" / "frontend").mkdir(parents=True)
    (root / ".claude" / "rules" / "genel.md").write_text("Her yerde: testsiz kod yok", "utf-8")
    (root / ".claude" / "rules" / "frontend" / "react.md").write_text(
        "---\npaths:\n  - src/**/*.tsx\n  - '*.css'\n---\nReact kuralı: hook adı use ile başlar",
        "utf-8",
    )
    (root / ".claude" / "rules" / "notlar.txt").write_text("md değil", "utf-8")
    return root


def test_kurallar_ozyinelemeli_kesfedilir_ve_paths_ayristirilir(proje):
    kurallar = discover_rules(proje, None)

    etiketler = {k.label: k for k in kurallar}
    assert set(etiketler) == {".claude/rules/genel.md", ".claude/rules/frontend/react.md"}
    assert etiketler[".claude/rules/genel.md"].paths == ()
    assert etiketler[".claude/rules/frontend/react.md"].paths == ("src/**/*.tsx", "*.css")
    assert all(not k.trusted for k in kurallar)


def test_kullanici_kurallari_guvenilir_etiketle_once_gelir(proje, tmp_path):
    ev = tmp_path / "ev"
    (ev / ".claude" / "rules").mkdir(parents=True)
    (ev / ".claude" / "rules" / "dil.md").write_text("Türkçe yanıt ver", "utf-8")

    kurallar = discover_rules(proje, ev)

    assert kurallar[0].label == "~/.claude/rules/dil.md"
    assert kurallar[0].trusted is True
    blok = unscoped_rules_block(kurallar)
    assert '<kullanici_kurali kaynak="~/.claude/rules/dil.md">' in blok
    assert blok.index("Türkçe yanıt ver") < blok.index("testsiz kod yok")


def test_paths_siz_kurallar_tur_basinda_paths_li_olanlar_girmez(proje):
    kurallar = discover_rules(proje, None)

    blok = unscoped_rules_block(kurallar)

    assert "testsiz kod yok" in blok
    assert "React kuralı" not in blok
    assert '<proje_kurali kaynak=".claude/rules/genel.md">' in blok


def test_paths_li_kural_yalniz_eslesen_dosyada_devreye_girer(proje):
    kurallar = discover_rules(proje, None)

    assert [k.label for k in scoped_rules_for(kurallar, "src/app/Hero.tsx")] == [
        ".claude/rules/frontend/react.md"
    ]
    assert scoped_rules_for(kurallar, "src/app/hero.py") == ()
    # Dizin parçası olmayan `*.css` deseni dosya adına da uygulanır (Claude Code).
    assert len(scoped_rules_for(kurallar, "styles/tema.css")) == 1


@pytest.mark.parametrize(
    ("desen", "yol", "beklenen"),
    [
        ("src/**/*.ts", "src/a/b/c.ts", True),
        ("src/**/*.ts", "src/c.ts", True),
        ("src/*.ts", "src/a/c.ts", False),
        ("**/*.test.ts", "app/x.test.ts", True),
        ("docs/", "docs/a/b.md", True),
        ("*.{ts,tsx}", "x.tsx", True),
        ("*.{ts,tsx}", "x.js", False),
    ],
)
def test_glob_eslesmesi(desen, yol, beklenen):
    assert matches_paths((desen,), yol) is beklenen


def test_kok_disina_cikan_sembolik_bag_okunmaz(proje, tmp_path):
    disari = tmp_path / "sizinti.md"
    disari.write_text("sızdırılan", "utf-8")
    (proje / ".claude" / "rules" / "bag.md").symlink_to(disari)

    kurallar = discover_rules(proje, None)

    assert all("bag.md" not in k.label for k in kurallar)


def test_kural_butcesi_asilinca_kirpma_bildirilir(proje):
    (proje / ".claude" / "rules" / "dev.md").write_text("k" * (MAX_RULES_CHARS * 2), "utf-8")

    blok = unscoped_rules_block(discover_rules(proje, None))

    assert blok.count("k") <= MAX_RULES_CHARS + 50
    assert "kırpıldı" in blok or "bütçe" in blok


def test_read_all_instructions_kurallari_da_ekler(proje):
    metin = read_all_instructions(proje, None)

    assert "testsiz kod yok" in metin
    assert "React kuralı" not in metin


def test_birlestirme_kapaliyken_kurallar_okunmaz(proje):
    metin = read_all_instructions(proje, None, instruction_merge=False)

    assert "testsiz kod yok" not in metin


def test_dosya_erisiminde_eslesen_kural_bir_kez_yuklenir(proje):
    (proje / "src" / "app").mkdir(parents=True)
    hedef = proje / "src" / "app" / "Hero.tsx"
    hedef.write_text("export const Hero = () => null;", "utf-8")
    kurallar = discover_rules(proje, None)
    yuklu: set[str] = set()

    ilk = load_nested_instructions(
        proje, hedef, loaded=yuklu, present=lambda rel: False, rules=kurallar
    )
    ikinci = load_nested_instructions(
        proje, hedef, loaded=yuklu, present=lambda rel: False, rules=kurallar
    )

    assert ilk is not None
    assert "React kuralı" in ilk.message.content
    assert ".claude/rules/frontend/react.md" in ilk.files
    assert ikinci is None
