"""Açık plan gerçek taşıma kanıtına bağlanır; kayıt plan beklentisini değiştiremez."""

from dataclasses import replace

import pytest

from fusion_cli.core.evidence import EvidenceStatus
from fusion_cli.core.repair_ledger import SourceFingerprint
from fusion_cli.engines.agent.remotion_bridge import (
    KitFramePlan,
    KitVerificationPlan,
    RemotionRuntimeVerifier,
)
from fusion_cli.tools.remotion_observe import RenderedFrame, RuntimeRecord


def _plan():
    return KitVerificationPlan(
        "index.ts", "Fusion", ("index.ts",), 10, (KitFramePlan(30, "feature", "proof.png"),)
    )


def _frame():
    sources = (SourceFingerprint("index.ts", "a" * 64),)
    runtime = RuntimeRecord("host", "Fusion", 30, ("feature",), True, True, (), True, True)
    return RenderedFrame("host", True, runtime, sources, sources)


@pytest.mark.parametrize(
    "problem",
    [
        "good",
        "wrong_frame",
        "wrong_scene",
        "wrong_composition",
        "wrong_session",
        "stale",
        "missing",
        "failed_render",
        "audit",
    ],
)
async def test_plan_gercek_kaydi_yalniz_dogru_baglamda_kabul_eder(tmp_path, problem):
    frame = _frame()
    if problem == "wrong_frame":
        frame = replace(frame, runtime=replace(frame.runtime, frame=31))
    if problem == "wrong_scene":
        frame = replace(frame, runtime=replace(frame.runtime, active_scenes=("other",)))
    if problem == "wrong_composition":
        frame = replace(frame, runtime=replace(frame.runtime, composition="Other"))
    if problem == "wrong_session":
        frame = replace(frame, runtime=replace(frame.runtime, session="old"))
    if problem == "stale":
        frame = replace(frame, source_after=(SourceFingerprint("index.ts", "b" * 64),))
    if problem == "missing":
        frame = replace(frame, runtime=None, rendered=False)
    if problem == "failed_render":
        frame = replace(frame, rendered=False)
    if problem == "audit":
        frame = replace(frame, rendered=False, runtime=replace(frame.runtime, findings=("taşma",)))

    async def transport(request):
        assert request.frame == 30 and request.composition == "Fusion"
        return frame

    result = await RemotionRuntimeVerifier(tmp_path, _plan(), transport=transport).verify()
    expected = EvidenceStatus.PASSED if problem == "good" else EvidenceStatus.UNVERIFIED
    if problem == "audit":
        expected = EvidenceStatus.FAILED
    assert result.evidence[0].status is expected
    assert result.evidence[0].behavioral is (expected is not EvidenceStatus.UNVERIFIED)


async def test_birden_cok_kare_sirali_ayri_plan_beklentisiyle_sinanir(tmp_path):
    calls = []
    plan = replace(_plan(), samples=(_plan().samples[0], KitFramePlan(60, "other", "proof2.png")))

    async def transport(request):
        calls.append(request.frame)
        frame = _frame()
        scene = "feature" if request.frame == 30 else "other"
        return replace(
            frame,
            session_id=str(request.frame),
            runtime=replace(
                frame.runtime,
                session=str(request.frame),
                frame=request.frame,
                active_scenes=(scene,),
            ),
        )

    result = await RemotionRuntimeVerifier(tmp_path, plan, transport=transport).verify()
    assert result.ok and len(result.evidence) == 2 and calls == [30, 60]
    assert all("tam video" in item.summary for item in result.evidence)


async def test_transport_istisnasi_dogrulanamadi_kanitidir(tmp_path):
    async def transport(request):
        raise OSError("renderer yok")

    result = await RemotionRuntimeVerifier(tmp_path, _plan(), transport=transport).verify()
    assert not result.ok and result.evidence[0].status is EvidenceStatus.UNVERIFIED


async def test_bos_ornek_plani_sessiz_basari_degil(tmp_path):
    result = await RemotionRuntimeVerifier(tmp_path, replace(_plan(), samples=())).verify()
    assert not result.ok and result.evidence[0].status is EvidenceStatus.UNVERIFIED


async def test_dizin_artefakti_transportu_baslatmaz(tmp_path):
    plan = replace(_plan(), samples=(KitFramePlan(30, "feature", "."),))
    result = await RemotionRuntimeVerifier(tmp_path, plan).verify()
    assert result.evidence[0].status is EvidenceStatus.UNVERIFIED


async def test_ayni_host_oturumu_yeniden_basari_sayilmaz(tmp_path):
    async def transport(request):
        return _frame()

    verifier = RemotionRuntimeVerifier(tmp_path, _plan(), transport=transport)
    assert (await verifier.verify()).ok
    assert not (await verifier.verify()).ok


async def test_sir_hedefli_symlink_transportu_baslatmaz(tmp_path):
    (tmp_path / ".env").write_text("test placeholder")
    (tmp_path / "index.ts").symlink_to(tmp_path / ".env")

    async def transport(request):
        pytest.fail("Sır hedefi okunamaz")

    result = await RemotionRuntimeVerifier(tmp_path, _plan(), transport=transport).verify()
    assert not result.ok


async def test_bridge_gercek_host_hash_nonce_ve_png_sinirini_baglar(tmp_path):
    import asyncio
    import json
    from functools import partial

    from fusion_cli.tools.remotion_observe import ProcessOutput, observe_frame

    (tmp_path / "index.ts").write_text("entry")

    async def runner(command, root, deadline_s):
        payload = json.loads(command[-1])
        from pathlib import Path

        await asyncio.to_thread(Path(payload["artifact"]).write_bytes, b"\x89PNG\r\n\x1a\n")
        record = {
            "session": payload["session"],
            "composition": payload["composition"],
            "frame": payload["frame"],
            "activeScenes": ["feature"],
            "featureReady": True,
            "auditSettled": True,
            "findings": [],
            "runtimeExecuted": True,
            "timelineSeen": True,
        }
        return ProcessOutput(0, json.dumps({"record": record, "rendered": True}), "")

    transport = partial(observe_frame, runner=runner)
    verifier = RemotionRuntimeVerifier(tmp_path, _plan(), transport=transport)
    result = await verifier.verify()
    assert result.ok and result.evidence[0].behavioral
    next_result = await verifier.verify()
    assert next_result.ok and next_result.evidence[0].behavioral
    assert result.evidence[0].artifact != next_result.evidence[0].artifact


@pytest.mark.parametrize("path", ["../outside.ts", ".env", "/absolute.ts"])
async def test_gecersiz_kaynak_kapsami_transportu_baslatmaz(tmp_path, path):
    async def transport(request):
        pytest.fail("Geçersiz kapsam taşıma başlatamaz")

    plan = replace(_plan(), sources=(path,))
    result = await RemotionRuntimeVerifier(tmp_path, plan, transport=transport).verify()
    assert result.evidence[0].status is EvidenceStatus.UNVERIFIED


async def test_build_verifier_acik_contract_yokken_genel_projeyi_degistirmez(tmp_path):
    from types import SimpleNamespace

    from fusion_cli.engines.agent.verification import build_verifier

    runtime = SimpleNamespace(
        verification_commands=(),
        web_verification=False,
        browser_verification=False,
        visual_verification=False,
    )
    config = SimpleNamespace(runtime=runtime)
    assert build_verifier(config, root=tmp_path, tool_context=None) is None
    verifier = build_verifier(
        config, root=tmp_path, tool_context=None, remotion_contract=replace(_plan(), samples=())
    )
    assert isinstance(verifier, RemotionRuntimeVerifier)
    assert not (await verifier.verify()).ok
