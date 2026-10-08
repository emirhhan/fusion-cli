"""Kit sözleşmesi yalnız taze, doğru render oturumunun gerçek gözlemini kabul eder."""

from __future__ import annotations

from dataclasses import replace

import pytest

from fusion_cli.core.evidence import EvidenceStatus
from fusion_cli.engines.agent.remotion_contract_verify import (
    ContractRequest,
    RemotionContractVerifier,
    RuntimeObservation,
    SourceFingerprint,
)

_MANIFEST = (SourceFingerprint("src/Video.tsx", "a" * 64),)
_REQUEST = ContractRequest(True, "Fusion", 30, "features", "session-new", "frame30.png", _MANIFEST)
_GOOD = RuntimeObservation(
    "Fusion",
    30,
    ("features",),
    "session-new",
    "observation-new",
    "frame30.png",
    _MANIFEST,
    _MANIFEST,
    True,
    True,
    True,
    True,
    active_scene_kinds=("feature",),
)


class Observer:
    def __init__(self, observation=_GOOD, error=False):
        self.observation = observation
        self.error = error
        self.calls = 0

    async def observe(self, request):
        self.calls += 1
        if self.error:
            raise RuntimeError("Gözlem taşıması yok")
        return self.observation


async def test_optout_gozlem_cagirmadan_genel_remotionu_korur():
    observer = Observer(error=True)
    result = await RemotionContractVerifier(replace(_REQUEST, enabled=False), observer).verify()
    assert result.ok and result.evidence == () and observer.calls == 0


async def test_gercek_taze_kare_kaniti_tam_render_basari_iddiasi_degildir():
    result = await RemotionContractVerifier(_REQUEST, Observer()).verify()
    assert result.ok
    assert result.evidence[0].status is EvidenceStatus.PASSED
    assert result.evidence[0].behavioral
    assert result.evidence[0].artifact == "frame30.png"
    assert "tam video" in result.evidence[0].summary


@pytest.mark.parametrize(
    "change",
    [
        {"runtime_executed": False},
        {"timeline_seen": False},
        {"feature_ready": False},
        {"audit_settled": False},
        {"composition_id": "Other"},
        {"frame": 31},
        {"session_id": "session-old"},
        {"artifact": "old.png"},
        {"active_scenes": ("other",)},
        {"source_after": (SourceFingerprint("src/Video.tsx", "b" * 64),)},
        {"source_before": ()},
    ],
)
async def test_statige_ve_eski_yanlis_gozleme_davranis_basari_yazilmaz(change):
    result = await RemotionContractVerifier(_REQUEST, Observer(replace(_GOOD, **change))).verify()
    assert not result.ok
    assert result.evidence[0].status is EvidenceStatus.UNVERIFIED
    assert not result.evidence[0].behavioral


async def test_gercek_audit_ihlali_basarisiz_davranis_kanitidir():
    result = await RemotionContractVerifier(
        _REQUEST, Observer(replace(_GOOD, audit_findings=("Taşma",)))
    ).verify()
    assert not result.ok
    assert result.evidence[0].status is EvidenceStatus.FAILED
    assert result.evidence[0].behavioral
    assert "Taşma" in result.findings[0]


async def test_tasima_hatasi_dogrulanamayan_kanit_uretir():
    result = await RemotionContractVerifier(_REQUEST, Observer(error=True)).verify()
    assert not result.ok
    assert result.evidence[0].status is EvidenceStatus.UNVERIFIED
    assert not result.evidence[0].behavioral


async def test_ayni_snapshot_yeniden_taze_kanit_sayilmaz():
    verifier = RemotionContractVerifier(_REQUEST, Observer())
    assert (await verifier.verify()).ok
    second = await verifier.verify()
    assert not second.ok and second.evidence[0].status is EvidenceStatus.UNVERIFIED


async def test_audit_iptali_hazir_marker_olmasa_da_gercek_basarisizliktir():
    observation = replace(
        _GOOD, audit_settled=False, feature_ready=False, audit_findings=("Kapasite",)
    )
    result = await RemotionContractVerifier(_REQUEST, Observer(observation)).verify()
    assert result.evidence[0].status is EvidenceStatus.FAILED
    assert result.evidence[0].behavioral


async def test_custom_sahne_feature_marker_zorunlulugu_uydurmaz():
    request = replace(_REQUEST, requires_feature=False)
    result = await RemotionContractVerifier(
        request, Observer(replace(_GOOD, feature_ready=False, active_scene_kinds=("custom",)))
    ).verify()
    assert result.ok and result.evidence[0].status is EvidenceStatus.PASSED


@pytest.mark.parametrize(
    "sources",
    [
        (),
        (SourceFingerprint("../outside.tsx", "a" * 64),),
        (SourceFingerprint("src/Video.tsx", "not-a-hash"),),
        _MANIFEST + _MANIFEST,
    ],
)
async def test_gecersiz_manifest_gozlem_bile_baslatmadan_dogrulanamadi_der(sources):
    observer = Observer()
    result = await RemotionContractVerifier(replace(_REQUEST, sources=sources), observer).verify()
    assert not result.ok and observer.calls == 0
    assert result.evidence[0].status is EvidenceStatus.UNVERIFIED


async def test_composite_kaniti_kaybetmez_ama_tam_video_iddia_etmez():
    from fusion_cli.engines.agent.verification import CompositeVerifier

    result = await CompositeVerifier((RemotionContractVerifier(_REQUEST, Observer()),)).verify()
    assert result.ok and len(result.evidence) == 1
    assert "tam video" in result.evidence[0].summary


@pytest.mark.parametrize("kinds", [(), ("custom",)])
async def test_feature_kopioitu_marker_ei_korvaa_timeline_descriptor_lajia(kinds):
    observation = replace(_GOOD, active_scene_kinds=kinds)
    result = await RemotionContractVerifier(_REQUEST, Observer(observation)).verify()
    assert not result.ok
    assert result.evidence[0].status is EvidenceStatus.UNVERIFIED
    assert not result.evidence[0].behavioral


async def test_typed_audit_failure_carries_real_observation_and_source_hashes():
    result = await RemotionContractVerifier(
        _REQUEST, Observer(replace(_GOOD, audit_findings=("Taşma",)))
    ).verify()
    failure = result.failure_evidence[0]
    assert failure.family == "layout_audit"
    assert failure.attempt_id == _GOOD.observation_id
    assert failure.sources[0].digest == _MANIFEST[0].sha256
    assert failure.sources[0].path == _MANIFEST[0].path


async def test_stale_audit_and_transport_failure_do_not_infer_product_origin():
    stale = replace(_GOOD, session_id="old", audit_findings=("Taşma",))
    result = await RemotionContractVerifier(_REQUEST, Observer(stale)).verify()
    assert result.failure_evidence == ()
    result = await RemotionContractVerifier(_REQUEST, Observer(error=True)).verify()
    assert result.failure_evidence == ()
