"""Host giriş dosyası sabit, içerik bileşeni düzenlenebilir kalır."""

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools.remotion_contract_check import check_packaged
from fusion_cli.tools.remotion_scaffold import scaffold_remotion


def _args():
    return {
        "path": "video",
        "composition_id": "Fusion",
        "timeout_s": 10,
        "scenes": [{"id": "intro", "kind": "custom", "duration": 90}],
    }


async def test_bootstrap_tsx_kayit_suresi_ve_editable_bilesen(tmp_path):
    context = ToolContext(root=tmp_path)
    assert (await scaffold_remotion(_args(), context)).ok
    contract = context.remotion_contract.registered
    assert contract.plan.entry == "src/index.tsx"
    source = (tmp_path / "video/src/index.tsx").read_text()
    assert 'id="Fusion"' in source and "durationInFrames={90}" in source
    assert "registerRoot(Root)" in source
    component = tmp_path / "video/src/Composition.tsx"
    component.write_text("export const Video = () => null; // düzenleme")
    assert (await scaffold_remotion(_args(), context)).ok
    check_packaged(tmp_path / "video", contract)
    assert all(item.path != "src/Composition.tsx" for item in contract.packaged_sources)


@pytest.mark.parametrize("change", ["rename", "mutate", "shadow"])
async def test_bootstrap_degisim_ve_import_golgesi_reddedilir(tmp_path, change):
    context = ToolContext(root=tmp_path)
    await scaffold_remotion(_args(), context)
    root = tmp_path / "video"
    entry = root / "src/index.tsx"
    if change == "rename":
        entry.rename(root / "src/moved.tsx")
    elif change == "mutate":
        entry.write_text("değişti")
    else:
        (root / "src/Composition.ts").write_text("export const Video=()=>null")
    with pytest.raises(ValueError):
        check_packaged(root, context.remotion_contract.registered)


@pytest.mark.parametrize("filename", ["index.tsx", "Composition.tsx", "index.ts", "Composition.js"])
async def test_bootstrap_mevcut_dosyayi_ezmez(tmp_path, filename):
    folder = tmp_path / "video/src"
    folder.mkdir(parents=True)
    existing = folder / filename
    existing.write_text("kullanıcı kaynağı")
    result = await scaffold_remotion(_args(), ToolContext(root=tmp_path))
    assert not result.ok and existing.read_text() == "kullanıcı kaynağı"
    assert not (folder / "kit").exists()


async def test_bootstrap_gözlem_sirasinda_degisirse_basari_tasinmaz(tmp_path):
    from fusion_cli.engines.agent.remotion_deferred import DeferredRemotionVerifier

    from .test_remotion_deferred import _transport

    context = ToolContext(root=tmp_path)
    await scaffold_remotion(_args(), context)

    async def transport(request):
        measured = await _transport(request)
        (request.root / "src/index.tsx").write_text("sonradan değişti")
        return measured

    result = await DeferredRemotionVerifier(
        tmp_path, context.remotion_contract, transport=transport
    ).verify()
    assert not result.ok and "Gözlem sırasında" in result.summary
