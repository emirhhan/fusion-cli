"""Alt dizin talimatları Claude Code kurallarıyla (#150).

Belge (memory, "How CLAUDE.md files load"): alt dizinin CLAUDE.md'si ve `.claude/rules/`
dosyaları o dizinde dosya okununca/yazılınca yüklenir; `cat`/`head` ile okuma da sayılır;
dosya başı sınır 200K pencerede 40.000, 1M pencerede 150.000 karakter.
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.engines.agent.nested_rules import (
    NESTED_MAX_CHARS,
    NESTED_MAX_CHARS_1M,
    max_chars_for_window,
    shell_read_target,
)
from fusion_cli.engines.agent.project_instructions import load_nested_instructions


def _yaz(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _yukle(root: Path, target: Path, **kw):  # type: ignore[no-untyped-def]
    return load_nested_instructions(root, target, loaded=set(), present=lambda _r: False, **kw)


def test_alt_dizinin_claude_rules_dosyalari_yuklenir(tmp_path: Path) -> None:
    web = tmp_path / "apps" / "web"
    _yaz(web / ".claude" / "rules" / "genel.md", "WEB GENEL KURAL")
    _yaz(web / ".claude" / "rules" / "tsx.md", "---\npaths: src/**/*.tsx\n---\nTSX KURALI")
    hedef = _yaz(web / "src" / "App.tsx", "x")
    diger = _yaz(web / "README.md", "x")

    yuk = _yukle(tmp_path, hedef)
    assert yuk is not None
    assert "WEB GENEL KURAL" in yuk.message.content and "TSX KURALI" in yuk.message.content

    yuk2 = _yukle(tmp_path, diger)
    assert yuk2 is not None
    assert "WEB GENEL KURAL" in yuk2.message.content and "TSX KURALI" not in yuk2.message.content


def test_nokta_ile_baslayan_dizin_atlanmaz_git_atlanir(tmp_path: Path) -> None:
    _yaz(tmp_path / ".github" / "CLAUDE.md", "GITHUB TALIMATI")
    _yaz(tmp_path / ".git" / "CLAUDE.md", "GIT TALIMATI")

    yuk = _yukle(tmp_path, _yaz(tmp_path / ".github" / "ci.yml", "x"))
    assert yuk is not None and "GITHUB TALIMATI" in yuk.message.content
    assert _yukle(tmp_path, _yaz(tmp_path / ".git" / "config", "x")) is None


def test_bir_milyon_pencerede_dosya_basi_sinir_buyur(tmp_path: Path) -> None:
    _yaz(tmp_path / "paket" / "CLAUDE.md", "a" * 60_000)
    hedef = _yaz(tmp_path / "paket" / "x.py", "x")

    kisa = _yukle(tmp_path, hedef)
    uzun = _yukle(tmp_path, hedef, max_chars=max_chars_for_window(1_000_000))

    assert kisa is not None and uzun is not None
    assert kisa.chars <= NESTED_MAX_CHARS < uzun.chars
    assert max_chars_for_window(200_000) == NESTED_MAX_CHARS
    assert max_chars_for_window(1_000_000) == NESTED_MAX_CHARS_1M


def test_kabukla_tek_dosya_okumasi_tetikleyici_sayilir() -> None:
    assert shell_read_target("cat packages/web/README.md") == "packages/web/README.md"
    assert shell_read_target("head -n 20 src/a.py") == "src/a.py"
    assert shell_read_target("cat a.md b.md") is None
    assert shell_read_target("cat a.md | grep x") is None
    assert shell_read_target("ls src") is None
