"""İşlem beyanı sezgisi: taşıdım/kaldırdım/uyguladım kanıt ister (A1-30)."""

from __future__ import annotations

import pytest

from fusion_cli.engines.agent.action_evidence import claimed_effects


@pytest.mark.parametrize(
    "metin",
    [
        "Dosyayı src/yeni/ klasörüne taşıdım.",
        "Eski dosyayı kaldırdım: app/old.py",
        "Yama dosyasını uyguladım.",
        "Modülü yeniden adlandırdım, dosya artık utils.py.",
    ],
)
def test_ek_fiiller_dosya_isleminde_kanit_ister(metin):
    assert claimed_effects(metin) == ("workspace_mutation",)


@pytest.mark.parametrize(
    "metin",
    [
        "İstersen dosyayı taşırım.",
        "Bu fonksiyonu şöyle yazdım: `def f(): ...`",
        "Neden kaldırdın diye sormuştun?",
        "Sorun kaldırım taşlarında değil.",
    ],
)
def test_yanlis_pozitif_alanlari_kapali_kalir(metin):
    assert claimed_effects(metin) == ()
