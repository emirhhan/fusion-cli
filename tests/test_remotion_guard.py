"""Kit kapısı değiştirilmeden içerik düzenlemesi devam eder."""

import pytest

from fusion_cli.core.errors import PathAccessError
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools.files import edit_file, multi_edit, writable_path, write_file
from fusion_cli.tools.remotion_scaffold import scaffold_remotion


async def _context(root):
    context = ToolContext(root=root)
    result = await scaffold_remotion(
        {
            "path": "video",
            "composition_id": "Video",
            "timeout_s": 10,
            "scenes": [{"id": "intro", "kind": "custom", "duration": 90}],
        },
        context,
    )
    assert result.ok
    return context


@pytest.mark.parametrize("tool", ["write", "edit", "multi"])
async def test_immutable_kit_yazma_duzenleme_degismeden_reddedilir(tmp_path, tool):
    context = await _context(tmp_path)
    path = tmp_path / "video/src/kit/LayoutAudit.tsx"
    original = path.read_bytes()
    args = {
        "path": str(path),
        "content": "kapı kaldırıldı",
        "old": "import React",
        "new": "silindi",
        "edits": [{"old": "import React", "new": "silindi"}],
    }
    with pytest.raises(PathAccessError):
        {"write": write_file, "edit": edit_file, "multi": multi_edit}[tool](args, context)
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    "relative",
    ["src/index.tsx", "src/index.ts", "src/Composition.js", "src/kit.tsx", "src/kit/fake.ts"],
)
async def test_bootstrap_ve_import_golgesi_mutasyondan_once_reddedilir(tmp_path, relative):
    context = await _context(tmp_path)
    with pytest.raises(PathAccessError):
        writable_path(context, f"video/{relative}")


async def test_symlink_alias_hashli_dosyayi_degistiremez(tmp_path):
    context = await _context(tmp_path)
    alias = tmp_path / "alias.tsx"
    alias.symlink_to(tmp_path / "video/src/kit/LayoutAudit.tsx")
    with pytest.raises(PathAccessError):
        writable_path(context, "alias.tsx")


async def test_composition_tema_ve_kitsiz_oturum_serbest(tmp_path):
    context = await _context(tmp_path)
    for relative in ("src/Composition.tsx", "src/kit/theme.ts"):
        assert writable_path(context, f"video/{relative}") == tmp_path / "video" / relative
    assert writable_path(ToolContext(root=tmp_path), "video/src/kit/LayoutAudit.tsx")


async def test_golge_symlinki_editable_bilesene_isaret_etse_de_reddedilir(tmp_path):
    context = await _context(tmp_path)
    (tmp_path / "video/src/kit.tsx").symlink_to(tmp_path / "video/src/Composition.tsx")
    with pytest.raises(PathAccessError):
        writable_path(context, "video/src/kit.tsx")
