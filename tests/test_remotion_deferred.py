"""Araçlardan önce kurulan kapı hostun geç sözleşmesini görür."""

import pytest

from fusion_cli.core.evidence import EvidenceStatus
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.remotion_deferred import DeferredRemotionVerifier
from fusion_cli.tools.remotion_observe import RenderedFrame, RuntimeRecord
from fusion_cli.tools.remotion_scaffold import scaffold_remotion


def _args():
    return {
        "path": "video",
        "composition_id": "Fusion",
        "timeout_s": 10,
        "scenes": [{"id": "intro", "kind": "feature", "duration": 120}],
    }


async def _transport(request):
    from fusion_cli.tools.job_evidence import prepare_manifest

    manifest = prepare_manifest(
        {"failure_check": "runtime", "failure_sources": list(request.sources)}, request.root
    )
    runtime = RuntimeRecord(
        str(request.frame), "Fusion", request.frame, ("intro",), True, True, (), True, True
    )
    return RenderedFrame(str(request.frame), True, runtime, manifest.sources, manifest.sources)


async def test_gec_iskele_kaydi_onceden_kurulan_kapiya_aktarilir(tmp_path):
    context = ToolContext(root=tmp_path)
    verifier = DeferredRemotionVerifier(tmp_path, context.remotion_contract, transport=_transport)
    assert (await verifier.verify()).ok
    assert (await scaffold_remotion(_args(), context)).ok
    result = await verifier.verify()
    assert result.ok and len(result.evidence) == 3


async def test_acik_kit_gereksinimi_eksik_kaydi_basari_saymaz(tmp_path):
    context = ToolContext(root=tmp_path)
    context.remotion_contract.require()
    result = await DeferredRemotionVerifier(tmp_path, context.remotion_contract).verify()
    assert not result.ok and result.evidence[0].status is EvidenceStatus.UNVERIFIED


async def test_genel_remotion_projesinde_acik_optin_yoksa_kanit_uydurulmaz(tmp_path):
    context = ToolContext(root=tmp_path)
    result = await DeferredRemotionVerifier(tmp_path, context.remotion_contract).verify()
    assert result.ok and not result.evidence


async def test_paket_kit_degistirilirse_runtime_baslatilmaz(tmp_path):
    context = ToolContext(root=tmp_path)
    await scaffold_remotion(_args(), context)
    (tmp_path / "video/src/kit/Timeline.tsx").write_text("kopya bileşen")

    async def transport(request):
        pytest.fail("Bozuk paket üzerinde render başlatılmaz")

    result = await DeferredRemotionVerifier(
        tmp_path, context.remotion_contract, transport=transport
    ).verify()
    assert not result.ok and result.evidence[0].status is EvidenceStatus.FAILED


@pytest.mark.parametrize("suffix", [".ts", ".tsx", ".js", ".jsx"])
async def test_iskele_sonrasi_kardes_kit_modulu_runtime_baslatmaz(tmp_path, suffix):
    context = ToolContext(root=tmp_path)
    await scaffold_remotion(_args(), context)
    (tmp_path / "video/src" / f"kit{suffix}").write_text("gölge modül")

    async def transport(request):
        pytest.fail("Gölge modül varken runtime başlatılmaz")

    result = await DeferredRemotionVerifier(
        tmp_path, context.remotion_contract, transport=transport
    ).verify()
    assert not result.ok and result.evidence[0].status is EvidenceStatus.FAILED


async def test_runtime_sirasinda_kardes_kit_modulu_eklenirse_kanit_gecersiz(tmp_path):
    context = ToolContext(root=tmp_path)
    await scaffold_remotion(_args(), context)

    async def transport(request):
        frame = await _transport(request)
        (request.root / "src/kit.tsx").write_text("sonradan gölge modül")
        return frame

    result = await DeferredRemotionVerifier(
        tmp_path, context.remotion_contract, transport=transport
    ).verify()
    assert not result.ok and result.evidence[-1].status is EvidenceStatus.FAILED


async def test_json_beklenti_degistiremez_nested_proje_koku_transporta_gider(tmp_path):
    context = ToolContext(root=tmp_path)
    await scaffold_remotion(_args(), context)
    (tmp_path / "video/fusion-contract.json").write_text('{"composition_id":"Other"}')

    async def transport(request):
        assert request.root == (tmp_path / "video").resolve()
        assert request.entry == "src/index.ts" and request.composition == "Fusion"
        return await _transport(request)

    result = await DeferredRemotionVerifier(
        tmp_path, context.remotion_contract, transport=transport
    ).verify()
    assert result.ok


async def test_paket_hashi_gözlem_sirasinda_degistiyse_basari_kaniti_kullanilmaz(tmp_path):
    context = ToolContext(root=tmp_path)
    await scaffold_remotion(_args(), context)

    async def transport(request):
        result = await _transport(request)
        (request.root / "src/kit/Timeline.tsx").write_text("sonradan değişti")
        return result

    result = await DeferredRemotionVerifier(
        tmp_path, context.remotion_contract, transport=transport
    ).verify()
    assert not result.ok and result.evidence[-1].status is EvidenceStatus.FAILED


async def test_gercek_agent_turunda_onceden_kurulan_kapi_scaffold_aracini_gorur(
    monkeypatch, tmp_path
):
    from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
    from fusion_cli.engines.agent.loop import AgentDeps, run_agent
    from fusion_cli.engines.agent.verification import build_verifier

    from .fakes import (
        AlwaysApprove,
        RecordingSink,
        ScriptedProvider,
        make_config,
        model_result,
        tool_call,
    )
    from .test_agent_loop import TAM_CEVAP, _kur, _Publisher

    context = ToolContext(root=tmp_path)
    config = make_config(
        memory_dir=tmp_path / "memory",
        source=tmp_path / "config.yaml",
        runtime={
            "web_verification": False,
            "browser_verification": False,
            "visual_verification": False,
        },
    )
    verifier = build_verifier(
        config,
        root=tmp_path,
        tool_context=context,
        remotion_state=context.remotion_contract,
        remotion_transport=_transport,
    )
    assert context.remotion_contract.registered is None
    provider = ScriptedProvider(
        [
            model_result(tool_calls=[tool_call("scaffold_remotion", **_args())]),
            model_result(
                tool_calls=[tool_call("write_file", path="video/src/index.ts", content="entry")]
            ),
            model_result(TAM_CEVAP),
        ]
    )
    _kur(monkeypatch, provider)
    deps = AgentDeps(
        config=config,
        publisher=_Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=context,
        verifier=verifier,
    )
    outcome = await run_agent("Fusion kit ile video oluştur", deps)
    assert outcome.ok and context.remotion_contract.registered is not None
    assert (await verifier.verify()).ok is False


async def test_cli_acik_kit_planini_araclardan_once_baglar(monkeypatch, tmp_path):
    from fusion_cli.cli import session
    from fusion_cli.engines.agent.loop import AgentOutcome

    from .fakes import make_config

    context = ToolContext(root=tmp_path)
    config = make_config(
        memory_dir=tmp_path / "memory",
        source=tmp_path / "config.yaml",
        runtime={
            "web_verification": False,
            "browser_verification": False,
            "visual_verification": False,
        },
        mcp_servers=(),
    )

    async def run(task, deps, **kwargs):
        assert deps.tool_context.remotion_contract is context.remotion_contract
        assert context.remotion_contract.is_required
        result = await deps.verifier.verify()
        assert not result.ok and result.evidence[0].status is EvidenceStatus.UNVERIFIED
        return AgentOutcome(final_text="Kit kaydı eksik", messages=[], ok=False)

    monkeypatch.setattr(session, "run_agent", run)
    outcome = await session.run_agent_task(
        "Yeni Fusion kit planı",
        config,
        sinks=(),
        prompter_factory=lambda drain: None,
        tool_context=context,
        root=tmp_path,
        interactive=False,
        require_remotion_kit=True,
    )
    assert not outcome.ok


async def test_canonical_kit_yerine_kopya_statikkayit_runtime_basari_sayilmaz(tmp_path):
    from dataclasses import replace

    context = ToolContext(root=tmp_path)
    await scaffold_remotion(_args(), context)

    async def transport(request):
        frame = await _transport(request)
        return replace(frame, runtime=replace(frame.runtime, runtime_executed=False))

    result = await DeferredRemotionVerifier(
        tmp_path, context.remotion_contract, transport=transport
    ).verify()
    assert not result.ok
    assert all(item.status is EvidenceStatus.UNVERIFIED for item in result.evidence)
