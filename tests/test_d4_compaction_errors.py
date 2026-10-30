"""Bağlam özeti sağlayıcı istisnasında turu düşürmez (A1-34)."""

from __future__ import annotations

import pytest

from fusion_cli.core.errors import ConfigError, ProviderError
from fusion_cli.engines.agent import compaction

from .fakes import make_config


@pytest.mark.parametrize("hata", [ConfigError("judge yok"), ProviderError("kapalı"), OSError("ağ")])
async def test_ozet_saglayici_istisnasi_bos_ozet_olur(monkeypatch, hata):
    def _kur(*args, **kwargs):
        raise hata

    monkeypatch.setattr(compaction, "build_provider", _kur)

    assert await compaction._summarize("iz", make_config(), None) == ""


async def test_ozet_cagrisi_istisna_firlatirsa_bos_ozet_olur(monkeypatch):
    class _Bozuk:
        async def complete(self, request):
            raise ProviderError("bağlantı koptu")

    monkeypatch.setattr(compaction, "build_provider", lambda *a, **k: _Bozuk())

    assert await compaction._summarize("iz", make_config(), None) == ""
