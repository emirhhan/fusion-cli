"""Görsel açıklaması reasoning bütçesinde kesilirse tek, sınırlı kurtarma."""

from __future__ import annotations

import asyncio

import pytest

from fusion_cli.core.types import ModelResult, ModelSpec
from fusion_cli.engines.agent import image_view

from .fakes import make_config


def _result(*, text="", ok=False, truncated=False, error=None):
    return ModelResult(
        name="goz",
        model="fake/vision",
        text=text,
        latency_ms=1,
        ok=ok,
        truncated=truncated,
        error=error,
    )


class _Provider:
    def __init__(self, *results, delay=0):
        self.results = results
        self.seen = []
        self.delay = delay

    async def complete(self, request):
        self.seen.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.results[len(self.seen) - 1]


async def _describe(tmp_path, monkeypatch, provider):
    path = tmp_path / "screen.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    monkeypatch.setattr("fusion_cli.providers.factory.build_provider", lambda *_a, **_kw: provider)
    config = make_config(vision=ModelSpec(name="goz", model="fake/vision"))
    return await image_view.describe_image(config, path, "Ekrandaki sayıyı oku.")


async def test_thinking_budget_exhaustion_gets_one_larger_attempt(tmp_path, monkeypatch):
    provider = _Provider(
        _result(truncated=True, error="runtime.max_tokens artır"),
        _result(text="Ekranda 391 yazıyor.", ok=True),
    )

    text, error = await _describe(tmp_path, monkeypatch, provider)

    assert text == image_view.VISION_OBSERVATION_LABEL + "Ekranda 391 yazıyor."
    assert error is None
    assert [request.max_tokens for request in provider.seen] == [200, 4096]
    assert all(request.max_retries == 0 for request in provider.seen)
    assert provider.seen[0].messages == provider.seen[1].messages


async def test_successful_short_vision_does_not_expand_budget(tmp_path, monkeypatch):
    provider = _Provider(_result(text="Kırmızı kare.", ok=True))

    text, error = await _describe(tmp_path, monkeypatch, provider)

    assert (text, error) == (image_view.VISION_OBSERVATION_LABEL + "Kırmızı kare.", None)
    assert len(provider.seen) == 1
    assert provider.seen[0].max_tokens == 200


async def test_nontruncation_failure_is_not_retried(tmp_path, monkeypatch):
    provider = _Provider(_result(error="410 Gone"))

    text, error = await _describe(tmp_path, monkeypatch, provider)

    assert text == ""
    assert "410 Gone" in error
    assert len(provider.seen) == 1


async def test_partial_description_is_never_accepted_as_complete(tmp_path, monkeypatch):
    provider = _Provider(
        _result(text="Ekranda", ok=True, truncated=True),
        _result(text="Ekranda 0 var.", ok=True),
    )

    assert await _describe(tmp_path, monkeypatch, provider) == (
        image_view.VISION_OBSERVATION_LABEL + "Ekranda 0 var.",
        None,
    )
    assert len(provider.seen) == 2


async def test_second_truncation_has_vision_specific_error_and_no_third_attempt(
    tmp_path, monkeypatch
):
    exhausted = _result(truncated=True, error="runtime.max_tokens artır")
    provider = _Provider(exhausted, exhausted)

    text, error = await _describe(tmp_path, monkeypatch, provider)

    assert text == ""
    assert "4096" in error
    assert "görsel" in error.lower()
    assert "runtime.max_tokens" not in error
    assert len(provider.seen) == 2


async def test_retry_uses_remaining_time_not_fresh_timeout(tmp_path, monkeypatch):
    provider = _Provider(
        _result(truncated=True),
        _result(text="0", ok=True),
        delay=0.01,
    )
    monkeypatch.setattr(image_view, "VISION_TIMEOUT_S", 1.0)

    assert await _describe(tmp_path, monkeypatch, provider) == (
        image_view.VISION_OBSERVATION_LABEL + "0",
        None,
    )
    assert 0 < provider.seen[1].timeout_s < provider.seen[0].timeout_s <= 1.0


async def test_completion_deadline_cancels_slow_provider(tmp_path, monkeypatch):
    provider = _Provider(_result(text="geç", ok=True), delay=10)
    monkeypatch.setattr(image_view, "VISION_TIMEOUT_S", 0.01)

    text, error = await _describe(tmp_path, monkeypatch, provider)

    assert text == ""
    assert "süre" in error.lower()
    assert len(provider.seen) == 1


async def test_cancellation_propagates_without_retry(tmp_path, monkeypatch):
    class _Cancelled(_Provider):
        async def complete(self, request):
            self.seen.append(request)
            raise asyncio.CancelledError

    provider = _Cancelled()
    with pytest.raises(asyncio.CancelledError):
        await _describe(tmp_path, monkeypatch, provider)
    assert len(provider.seen) == 1


async def test_observation_has_provenance_and_preserves_incomplete_expression(
    tmp_path, monkeypatch
):
    provider = _Provider(
        _result(text="visible_text: 17×23−\ndescription: calculator\nuncertainty: none", ok=True)
    )

    text, error = await _describe(tmp_path, monkeypatch, provider)

    assert error is None
    assert text.startswith(image_view.VISION_OBSERVATION_LABEL)
    assert "17×23−" in text
    assert "391" not in text
    system, user = provider.seen[0].messages
    assert system.role == "system"
    assert not system.images
    assert user.role == "user"
    assert user.content == "Ekrandaki sayıyı oku."
    assert user.images[0].startswith("data:image/png;base64,")
