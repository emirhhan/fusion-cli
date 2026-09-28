"""Model sağlık sondası önbelleği — ağsız, sahte saatle."""

from __future__ import annotations

from fusion_cli.providers import health_cache


class _SahteSaat:
    def __init__(self, now: float) -> None:
        self._now = now

    def now(self) -> float:
        return self._now

    def monotonic(self) -> float:
        return self._now


def test_hic_sondanmamis_model_saglikli_sayilmaz_ve_sagliksiz_da_sayilmaz(tmp_path):
    yol = tmp_path / "model_health.json"

    assert health_cache.is_known_unhealthy(yol, "nvidia_nim/z-ai/glm-5.3") is False


def test_taze_basarisiz_sonuc_sagliksiz_isaretlenir(tmp_path):
    yol = tmp_path / "model_health.json"
    saat = _SahteSaat(1_000.0)

    health_cache.record(yol, "nvidia_nim/z-ai/glm-5.3", ok=False, detail="zaman aşımı", clock=saat)

    assert health_cache.is_known_unhealthy(yol, "nvidia_nim/z-ai/glm-5.3", clock=saat) is True


def test_basarili_sonuc_sagliksiz_sayilmaz(tmp_path):
    yol = tmp_path / "model_health.json"
    saat = _SahteSaat(1_000.0)

    health_cache.record(yol, "nvidia_nim/nvidia/nemotron-3-super-120b-a12b", ok=True, clock=saat)

    assert (
        health_cache.is_known_unhealthy(
            yol, "nvidia_nim/nvidia/nemotron-3-super-120b-a12b", clock=saat
        )
        is False
    )


def test_suresi_dolmus_sagliksiz_sonuc_artik_sayilmaz(tmp_path):
    yol = tmp_path / "model_health.json"
    kayit_zamani = _SahteSaat(1_000.0)
    health_cache.record(yol, "nvidia_nim/z-ai/glm-5.3", ok=False, clock=kayit_zamani)

    okuma_zamani = _SahteSaat(1_000.0 + 100_000.0)

    assert (
        health_cache.is_known_unhealthy(
            yol, "nvidia_nim/z-ai/glm-5.3", ttl_s=21_600.0, clock=okuma_zamani
        )
        is False
    )


def test_bozuk_dosya_cokmeden_bos_onbellek_sayilir(tmp_path):
    yol = tmp_path / "model_health.json"
    yol.write_text("bu gecerli bir json degil {", encoding="utf-8")

    assert health_cache.load(yol) == {}
    assert health_cache.is_known_unhealthy(yol, "nvidia_nim/z-ai/glm-5.3") is False


def test_kayit_var_olan_diger_modelleri_korur(tmp_path):
    yol = tmp_path / "model_health.json"
    saat = _SahteSaat(1_000.0)

    health_cache.record(yol, "model-a", ok=True, clock=saat)
    health_cache.record(yol, "model-b", ok=False, clock=saat)

    entries = health_cache.load(yol)
    assert set(entries) == {"model-a", "model-b"}
    assert entries["model-a"].ok is True
    assert entries["model-b"].ok is False
