"""Plan ÖNCESİNDE de düşen kapı, adımı çıktısı değişti diye düşürmemeli.

Ölçüldü (7 Eylül canlı Godot koşusu): kapı zaman aşımına uğradığında bulgu metni
"asılmadan önce şunu söyledi:" kuyruğunu taşıyor ve bu kuyruk her koşuda birebir
aynı olmuyor. Baseline karşılaştırması METNE bakıyordu; aynı kapı, aynı sebeple
düşmesine rağmen "yeni kırılma" sayılıp adımı öldürüyordu.

Soru "aynı cümle mi" değil, "AYNI KAPI mı" olmalıdır.
"""

from __future__ import annotations

from fusion_cli.engines.agent.step_verification import new_findings


def test_ayni_komutun_farkli_ciktisi_yeni_kirilma_sayilmaz():
    onceki = ("komut zaman aşımına uğradı (120.0s): godot --headless --path . --quit\nA",)
    simdiki = ("komut zaman aşımına uğradı (120.0s): godot --headless --path . --quit\nB",)

    assert new_findings(simdiki, onceki) == ()


def test_birebir_ayni_bulgu_yeni_sayilmaz():
    assert new_findings(("aynı",), ("aynı",)) == ()


def test_baska_bir_kapinin_bulgusu_yeni_sayilir():
    onceki = ("komut zaman aşımına uğradı (120.0s): godot --headless --path . --quit",)
    simdiki = ("komut başarısız (1): pytest -q\nE   assert 0",)

    assert new_findings(simdiki, onceki) == simdiki


def test_komut_icermeyen_bulgu_metinle_karsilastirilir():
    assert new_findings(("sahne script ile uyumsuz",), ("başka bulgu",)) == (
        "sahne script ile uyumsuz",
    )


async def test_command_failures_keep_typed_product_infrastructure_and_provider_origins(tmp_path):
    import shlex
    import sys

    from fusion_cli.core.repair_ledger import FailureOrigin
    from fusion_cli.engines.agent.verification import CommandVerifier

    for script, origin in (
        ("raise AssertionError('expected 2 got 1')", FailureOrigin.PRODUCT),
        ("raise RuntimeError('provider quota exceeded HTTP 429')", FailureOrigin.PROVIDER),
    ):
        command = f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"
        result = await CommandVerifier((command,), cwd=str(tmp_path), timeout_s=3).verify()
        assert result.failure_evidence
        assert result.failure_evidence[0].origin is origin
        assert result.failure_evidence[0].environment.cwd == str(tmp_path)
    missing = await CommandVerifier(
        ("fusion_fixture_missing_runner",), cwd=str(tmp_path), timeout_s=3
    ).verify()
    assert missing.failure_evidence[0].origin is FailureOrigin.INFRASTRUCTURE
    wrong_cwd = await CommandVerifier(
        (f"{shlex.quote(sys.executable)} -c 'pass'",),
        cwd=str(tmp_path / "missing"),
        timeout_s=3,
    ).verify()
    assert wrong_cwd.failure_evidence[0].origin is FailureOrigin.INFRASTRUCTURE


async def test_composite_retains_environment_failures_and_related_source_hashes(tmp_path):
    import shlex
    import sys

    from fusion_cli.core.repair_ledger import FailureOrigin
    from fusion_cli.engines.agent.verification import CommandVerifier, CompositeVerifier

    source = tmp_path / "test_fixture.py"
    source.write_text("assert 2 == 1\n")
    command = f"{shlex.quote(sys.executable)} test_fixture.py"
    verifier = CompositeVerifier((CommandVerifier((command,), cwd=str(tmp_path), timeout_s=3),))
    before = await verifier.verify()
    failure = before.failure_evidence[0]
    assert failure.origin is FailureOrigin.PRODUCT
    assert failure.family == "AssertionError"
    assert failure.sources[0].path == "test_fixture.py"
    source.write_text("assert 3 == 1\n")
    after = await verifier.verify()
    assert after.failure_evidence[0].sources != failure.sources
    assert after.failure_evidence[0].attempt_id != failure.attempt_id
    assert verifier.evidence_environment().cwd == str(tmp_path)
