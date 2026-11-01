"""acceptEdits kabuk kapsamı Claude Code ile birebir (#53).

Kaynak: https://code.claude.com/docs/en/permission-modes#auto-approve-file-edits-with-acceptedits-mode
"""

from __future__ import annotations

import pytest

from fusion_cli.tools.accept_edits_scope import accept_edits_allows


@pytest.mark.parametrize(
    ("komut", "beklenen"),
    [
        ("mkdir -p src/x", True),
        ("rm a.txt", True),
        ("rmdir bos", True),
        ("mv a b", True),
        ("cp a b", True),
        ("sed -i s/a/b/ f", True),
        ("touch a b", True),
        ("timeout 5 rm a", True),
        ("LANG=C sed -i s/a/b/ f", True),
        ("git status", True),
        ("ls && rm a", True),
        ("timeout 5 touch a", False),
        ("touch -t 1 a", False),
        ("LD_PRELOAD=x rm a", False),
        ("pytest -q", False),
        ("npm test", False),
        ("mv a /etc/x", False),
        ("cp a ~/b", False),
        ("echo x > /etc/a", False),
        ("rm $(cat liste)", False),
    ],
)
def test_accept_edits_kabuk_kapsami(tmp_path, komut, beklenen):
    assert accept_edits_allows(komut, tmp_path) is beklenen


def test_ek_dizin_icindeki_yol_kapsamda(tmp_path):
    ek = tmp_path.parent / "ek-dizin"
    assert accept_edits_allows(f"cp a {ek}/b", tmp_path) is False
    assert accept_edits_allows(f"cp a {ek}/b", tmp_path, (ek,)) is True


@pytest.mark.parametrize(
    ("komut", "beklenen"),
    [
        ("cp --target-directory=/etc f", False),
        ("mv --target-directory=/tmp f", False),
        ("cp -t/etc f", False),
        ("cp -vt/etc f", False),
        ("cp --target-directory=alt f", True),
        ("sed -n 'w /tmp/leak' f", False),
        ("sed -n '1e id' f", False),
        ("sed -i 's/a/b/e' f", False),
        ("sed -i 's/a/b/w /tmp/x' f", False),
        ("sed -f betik.sed -i f", False),
        ("sed -i '' 's/a/b/e' f", False),
        ("sed -i.bak 's/a/b/g' f", True),
        ("sed -Ei 's/a+/b/' f", True),
        ("sed -i '' 's/a/b/' f", True),
        ("sed --in-place=.bak -e 's/a/b/' f", True),
        ("sed -i/etc/* s/a/b/ f", False),
    ],
)
def test_hedef_dizin_secenegi_ve_sed_betigi(tmp_path, komut, beklenen):
    """İnceleme (1 Kasım): `--target-directory=` ve sed `e`/`w` acceptEdits sınırını aşıyordu."""
    assert accept_edits_allows(komut, tmp_path) is beklenen, komut
