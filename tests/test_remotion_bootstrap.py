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


async def test_tsconfig_uyumlu_host_iskele_tekrari_ve_mevcut_dosya_korunur(tmp_path):
    import json

    context = ToolContext(root=tmp_path)
    assert (await scaffold_remotion(_args(), context)).ok
    path = tmp_path / "video/tsconfig.json"
    config = json.loads(path.read_text())
    options = config["compilerOptions"]
    assert options["moduleResolution"] == "Bundler"
    assert options["strict"] and options["noEmit"]
    assert "baseUrl" not in options and "paths" not in options
    assert (await scaffold_remotion(_args(), context)).ok
    path.write_text('{"compilerOptions":{"strict":false}}')
    assert not (await scaffold_remotion(_args(), context)).ok
    assert json.loads(path.read_text())["compilerOptions"]["strict"] is False


async def test_farkli_mevcut_tsconfig_hicbir_kit_dosyasi_yazmaz(tmp_path):
    path = tmp_path / "video/tsconfig.json"
    path.parent.mkdir()
    path.write_text("mevcut proje")
    assert not (await scaffold_remotion(_args(), ToolContext(root=tmp_path))).ok
    assert path.read_text() == "mevcut proje" and not (path.parent / "src").exists()


async def test_scaffold_tsconfig_gercek_yerel_typescript_ile_derlenir(tmp_path):
    import asyncio
    import json
    from pathlib import Path

    from fusion_cli.tools.remotion_bootstrap import tsconfig_source

    test_path = await asyncio.to_thread(Path(__file__).resolve)
    compiler = test_path.parents[1] / "app/node_modules/typescript/bin/tsc"
    if not compiler.exists():
        pytest.skip("Yerel TypeScript yok; kurulum yapılmaz.")
    (tmp_path / "tsconfig.json").write_bytes(tsconfig_source())
    (tmp_path / "src").mkdir()
    (tmp_path / "src/minimal.tsx").write_text(
        "declare const React: {createElement: unknown};\n"
        "declare global {namespace JSX { interface IntrinsicElements {div: object;} }}\n"
        "export const Video = () => <div/>;\n"
    )
    process = await asyncio.create_subprocess_exec(
        "node",
        str(compiler),
        "-p",
        str(tmp_path / "tsconfig.json"),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    assert process.returncode == 0, (stdout + stderr).decode()
    assert json.loads((tmp_path / "tsconfig.json").read_text())["include"] == ["src"]


def test_beceri_bos_projede_once_host_iskele_sonra_bagimlilik_kurar():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    skill = (root / "src/fusion_cli/config/skills/remotion-video/SKILL.md").read_text()
    assert "create-video" not in skill
    assert skill.index("scaffold_remotion(") < skill.index("npm install")
    assert len(skill) <= 4000
