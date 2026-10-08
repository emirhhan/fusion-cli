"""Host iskele kaydı üretimden önce sabitlenir; JSON başarı beyanı değildir."""

import hashlib
import json

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools.remotion_scaffold import scaffold_remotion


def _args():
    return {
        "path": "video",
        "composition_id": "Fusion",
        "timeout_s": 10,
        "scenes": [
            {"id": "intro", "kind": "feature", "duration": 120},
            {"id": "outro", "kind": "custom", "duration": 90},
        ],
    }


async def test_kit_kopyasi_sabit_host_plani_ve_ornekleri_kaydeder(tmp_path):
    context = ToolContext(root=tmp_path)
    carrier = context.remotion_contract
    assert carrier.registered is None
    result = await scaffold_remotion(_args(), context)
    assert result.ok and len(result.output) < 500
    contract = context.remotion_contract.registered
    assert context.remotion_contract is carrier
    assert contract is not None
    assert contract.plan.composition_id == "Fusion"
    assert [(sample.frame, sample.scene_id) for sample in contract.plan.samples] == [
        (0, "intro"),
        (60, "intro"),
        (119, "intro"),
        (120, "outro"),
        (165, "outro"),
        (209, "outro"),
    ]
    assert contract.plan.samples[3].requires_feature is False
    assert (tmp_path / "video/src/kit/Timeline.tsx").exists()
    assert contract.packaged_sources and context.touched
    assert contract.project_dir == "video"
    for source in contract.packaged_sources:
        assert (
            hashlib.sha256((tmp_path / "video" / source.path).read_bytes()).hexdigest()
            == source.digest
        )


async def test_tema_degisebilir_ama_diger_paket_hashleri_sabit_kalir(tmp_path):
    context = ToolContext(root=tmp_path)
    await scaffold_remotion(_args(), context)
    theme = tmp_path / "video/src/kit/theme.ts"
    theme.write_text("marka teması")
    assert (await scaffold_remotion(_args(), context)).ok
    assert theme.read_text() == "marka teması"
    assert all(
        source.path != "src/kit/theme.ts"
        for source in context.remotion_contract.registered.packaged_sources
    )


@pytest.mark.parametrize(
    "scene",
    [
        {"id": "x", "kind": "feature", "duration": True},
        {"id": "../x", "kind": "feature", "duration": 120},
        {"id": "x", "kind": "unknown", "duration": 120},
        {"id": "x", "kind": "feature", "duration": 120, "passed": True},
    ],
)
async def test_gecersiz_sahne_plani_dosya_yazmaz(tmp_path, scene):
    context = ToolContext(root=tmp_path)
    assert not (await scaffold_remotion({**_args(), "scenes": [scene]}, context)).ok
    assert not list(tmp_path.iterdir()) and context.remotion_contract.registered is None


async def test_metadata_sir_symlinki_okunmadan_reddedilir(tmp_path):
    (tmp_path / ".env").write_text("test placeholder")
    target = tmp_path / "video"
    target.mkdir()
    (target / "fusion-contract.json").symlink_to(tmp_path / ".env")
    context = ToolContext(root=tmp_path)
    assert not (await scaffold_remotion(_args(), context)).ok
    assert context.remotion_contract.registered is None
    assert not (target / "src").exists()


async def test_paket_indexini_golgeleyen_ek_kit_dosyasi_korunup_reddedilir(tmp_path):
    target = tmp_path / "video/src/kit/index.tsx"
    target.parent.mkdir(parents=True)
    target.write_text("özgün modül")
    context = ToolContext(root=tmp_path)
    assert not (await scaffold_remotion(_args(), context)).ok
    assert target.read_text() == "özgün modül"
    assert context.remotion_contract.registered is None


def test_arac_kayitli_yerel_degistirici_ve_dosya_ailesinde():
    from fusion_cli.core.tools import ToolFamily, tool_family
    from fusion_cli.tools.builtin import build_registry

    tool = build_registry().get("scaffold_remotion")
    assert tool is not None and tool.mutating
    assert tool_family("scaffold_remotion") is ToolFamily.FILES


def test_kisa_beceri_araci_ve_son_dogrulama_talimatini_kirpmaz():
    from fusion_cli.engines.agent.expertise import expertise_hint

    hint = expertise_hint("Remotion video")
    assert hint is not None and "scaffold_remotion" in hint
    assert "animasyon çalışmıyor demektir." in hint
    assert "cp -R" not in hint


async def test_dosya_json_degistirilmesi_host_beklentisini_degistiremez(tmp_path):
    context = ToolContext(root=tmp_path)
    await scaffold_remotion(_args(), context)
    before = context.remotion_contract.registered
    (tmp_path / "video/fusion-contract.json").write_text(json.dumps({"scenes": []}))
    assert context.remotion_contract.registered is before


async def test_degistirilmis_kit_dosyasi_ezilmez_ve_sozlesme_kaydedilmez(tmp_path):
    context = ToolContext(root=tmp_path)
    target = tmp_path / "video/src/kit/Timeline.tsx"
    target.parent.mkdir(parents=True)
    target.write_text("kullanıcının mevcut içeriği")
    result = await scaffold_remotion(_args(), context)
    assert not result.ok and target.read_text() == "kullanıcının mevcut içeriği"
    assert context.remotion_contract.registered is None
    assert not (target.parent / "index.ts").exists()


async def test_farkli_ikinci_plan_ilk_beklentiyi_sessizce_degistiremez(tmp_path):
    context = ToolContext(root=tmp_path)
    await scaffold_remotion(_args(), context)
    original = context.remotion_contract.registered
    args = _args()
    args["composition_id"] = "Other"
    result = await scaffold_remotion(args, context)
    assert not result.ok and context.remotion_contract.registered is original


async def test_sir_ve_kokdisi_hedef_araci_baslatmaz(tmp_path):
    for path in ("../outside", ".env", "/absolute"):
        context = ToolContext(root=tmp_path)
        args = {**_args(), "path": path}
        assert not (await scaffold_remotion(args, context)).ok
        assert context.remotion_contract.registered is None


async def test_alt_ajan_yazma_alani_disinda_kit_yazilmaz(tmp_path):
    context = ToolContext(root=tmp_path, write_scope=(tmp_path / "other",))
    assert not (await scaffold_remotion(_args(), context)).ok
    assert not (tmp_path / "video").exists()


async def test_iptal_edilmis_baglam_kit_yazmaz(tmp_path):
    context = ToolContext(root=tmp_path)
    context.cancelled.set()
    assert not (await scaffold_remotion(_args(), context)).ok
    assert not (tmp_path / "video").exists()
