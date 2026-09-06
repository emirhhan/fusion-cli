"""Bütünlük sınıfı gerçek turda ayrı kurtarma üretir.

Sınıflandırma tek başına işe yaramaz: kapanmamış blokta sözleşme hatırlatılmalı,
kesilmiş yanıtta "kaldığın yerden devam et" denmeli. İkisini aynı nota bağlamak,
yapılan işi çöpe atıyor ya da modele yanlış şeyi düzelttiriyordu.
"""

from __future__ import annotations

from fusion_cli.core.web_response import ResponseIntegrity
from fusion_cli.engines.agent.reflexion import integrity_note


def test_kesilmis_yanit_devam_notu_alir():
    not_ = integrity_note(ResponseIntegrity.TRUNCATED)

    assert not_ is not None
    assert "devam" in not_.content.casefold()


def test_kapanmamis_blok_sozlesme_notu_alir():
    not_ = integrity_note(ResponseIntegrity.UNCLOSED_BLOCK)

    assert not_ is not None
    icerik = not_.content.casefold()
    assert "bloğu" in icerik
    assert "tam olarak" in icerik or "kapat" in icerik


def test_bos_yanit_sadelestirme_notu_alir():
    not_ = integrity_note(ResponseIntegrity.EMPTY)

    assert not_ is not None
    assert "tek" in not_.content.casefold() or "kısa" in not_.content.casefold()


def test_saglam_yanit_not_almaz():
    assert integrity_note(ResponseIntegrity.OK) is None
