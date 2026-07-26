"""Sağlayıcı kurma — öncelik penceresinin hangi kaynaktan geldiği.

Pencere rolün hızına aittir, motorun geneline değil. Bu dosya kompozisyonun tek
yerinde (`build_provider`) bu önceliğin bozulmadığını doğrular: hata bu satırda
oluştuğunda kullanıcı hiçbir uyarı almadan yanlış modelin cevabını alır.
"""

from __future__ import annotations

from fusion_cli.core.types import ModelSpec
from fusion_cli.providers.factory import build_provider

#: Genel varsayılan ile rolün kendi değeri; karışmamaları için bilerek farklı.
GENEL_PENCERE = 2.5
ROL_PENCERESI = 17.4


def _pencere(spec: ModelSpec) -> float:
    """Kurulan sağlayıcı yığınından hedged katmanın penceresini oku."""
    provider = build_provider(spec, publisher=None, hedge_delay_s=GENEL_PENCERE)
    return provider._hedge_delay_s  # type: ignore[attr-defined]


def test_rolun_kendi_penceresi_genel_varsayilani_ezer():
    spec = ModelSpec(
        name="yavas-ama-secilmis",
        model="nvidia_nim/z-ai/glm-5.2",
        fallback=("openrouter/openai/gpt-oss-20b:free",),
        hedge_delay_s=ROL_PENCERESI,
    )

    assert _pencere(spec) == ROL_PENCERESI


def test_penceresi_olmayan_rol_genel_varsayilana_duser():
    """Ölçümü olmayan roller için davranış birebir korunur."""
    spec = ModelSpec(name="olcumsuz", model="nvidia_nim/poolside/laguna-xs-2.1")

    assert _pencere(spec) == GENEL_PENCERE


def test_sifir_pencere_genel_varsayilana_dusmez():
    """`0` geçerli bir tercihtir ("yedekler hemen başlasın"), eksik değer değildir.

    Doğruluk/yanlışlık ölçütü kullanılsaydı 0 sessizce 2.5'e dönerdi ve kullanıcının
    açıkça yazdığı tercih tersine çevrilirdi.
    """
    spec = ModelSpec(name="yarissin", model="nvidia_nim/openai/gpt-oss-120b", hedge_delay_s=0.0)

    assert _pencere(spec) == 0.0
