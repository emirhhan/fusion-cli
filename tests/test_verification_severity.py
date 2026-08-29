from __future__ import annotations

from fusion_cli.core.tools import ToolContext
from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent.browser_verify import (
    PageObservation,
    page_findings_by_severity,
)
from fusion_cli.engines.agent.verification import (
    CompositeVerifier,
    WebVerifier,
    resolve_turn_success,
)
from fusion_cli.engines.agent.web_verify import inspect_web_output_by_severity


def test_main_eksikligi_warning_ama_blocking_degil():
    blocking, warnings, advisories = inspect_web_output_by_severity(
        {"index.html": ("<html><body><header>x</header><section>icerik</section></body></html>")}
    )

    assert blocking == ()
    assert any("<main>" in item for item in warnings)
    assert advisories == ()


def test_spacing_advisory_ama_blocking_degil():
    blocking, warnings, advisories = inspect_web_output_by_severity(
        {
            "index.html": (
                '<html><head><link rel="stylesheet" href="style.css"></head>'
                "<body><main>x</main></body></html>"
            ),
            "style.css": ".x { padding: 13px; }",
        }
    )

    assert blocking == ()
    assert warnings == ()
    assert any("4'lük" in item for item in advisories)


def test_kirik_gorsel_blocking_kalir():
    blocking, warnings, advisories = inspect_web_output_by_severity(
        {
            "index.html": (
                '<html><body><main><img src="https://via.placeholder.com/100"></main></body></html>'
            )
        }
    )

    assert any("placeholder" in item for item in blocking)
    assert warnings == ()
    assert advisories == ()


def test_browser_overflow_blocking_touch_target_warning():
    observation = PageObservation(
        name="index.html",
        overflowing=((375, 590),),
        small_targets=(("button.x", 18, 18),),
    )

    blocking, warnings, advisories = page_findings_by_severity((observation,))

    assert any("taşma" in item.lower() for item in blocking)
    assert any("dokunma" in item.lower() for item in warnings)
    assert advisories == ()


async def test_web_verifier_sadece_main_icin_turu_dusurmez(tmp_path):
    path = tmp_path / "index.html"
    path.write_text(
        "<html><body><section>icerik</section></body></html>",
        encoding="utf-8",
    )

    context = ToolContext(root=tmp_path)
    context.touched.add(path)

    result = await WebVerifier(context).verify()

    assert result.ok
    assert result.findings == ()
    assert any("<main>" in item for item in result.warnings)


class _StaticVerifier:
    def __init__(self, result: VerificationResult) -> None:
        self._result = result

    async def verify(self) -> VerificationResult:
        return self._result


async def test_composite_nonblocking_notlari_kaybetmez():
    verifier = CompositeVerifier(
        (
            _StaticVerifier(
                VerificationResult(
                    ok=True,
                    warnings=("semantic eksik",),
                    advisories=("spacing önerisi",),
                )
            ),
            _StaticVerifier(VerificationResult(ok=True)),
        )
    )

    result = await verifier.verify()

    assert result.ok
    assert result.warnings == ("semantic eksik",)
    assert result.advisories == ("spacing önerisi",)


def test_nonblocking_verification_learning_basarisini_dusurmez():
    verification = VerificationResult(
        ok=True,
        warnings=("semantic eksik",),
        advisories=("spacing önerisi",),
    )

    assert resolve_turn_success(
        outcome_ok=True,
        hit_step_limit=False,
        verification=verification,
    )
