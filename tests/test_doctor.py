"""`fusion doctor` — kurulum tanısı.

Varsayılan çalışma AĞSIZDIR: tanı almak kota harcamamalı. Canlı sağlayıcı testi
yalnızca `--live` ile ve ayrı işaretli integration testinde yapılır.
"""

from __future__ import annotations

import json

from fusion_cli.cli import doctor


def test_tani_ag_cagrisi_yapmadan_calisir(monkeypatch):
    """Varsayılan `fusion doctor` sağlayıcıya HİÇ istek atmamalı."""

    def _patlat(*args, **kwargs):
        raise AssertionError("doctor varsayılan modda ağa çıkmamalı")

    monkeypatch.setattr("httpx.Client", _patlat)

    rapor = doctor.diagnose(live=False)

    assert rapor.checks, "en az bir kontrol olmalı"


def test_anahtar_degeri_hicbir_ciktida_gorunmez(monkeypatch):
    """Tanı çıktısı anahtarın kendisini ASLA göstermez; yalnızca varlığını."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-COKGIZLIANAHTAR123456")
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "nvapi-COKGIZLIANAHTAR123456")

    rapor = doctor.diagnose(live=False)
    metin = json.dumps(doctor.to_dict(rapor), ensure_ascii=False)

    assert "COKGIZLIANAHTAR" not in metin
    assert "ayarlı" in metin


def test_anahtar_yokken_ne_yapilacagi_yazilir(monkeypatch):
    """ "Başarısız" demek yetmez: kullanıcı ne çalıştıracağını bilmeli."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("NVIDIA_NIM_API_KEY", raising=False)
    monkeypatch.setattr(doctor, "load_environment", lambda: None)

    rapor = doctor.diagnose(live=False)

    anahtar = next(c for c in rapor.checks if c.name == "OPENROUTER_API_KEY")
    assert anahtar.ok is False
    assert anahtar.remedy, "çözüm satırı olmalı"
    assert "fusion setup" in anahtar.remedy


def test_json_ciktisi_ayristirilabilir():
    """Betikler için: `fusion doctor --json` geçerli JSON üretmeli."""
    veri = doctor.to_dict(doctor.diagnose(live=False))

    assert json.loads(json.dumps(veri))["checks"]
    assert veri["ready"] in {"ready", "partially_ready", "not_ready"}


def test_surum_ve_ortam_bilgisi_raporlanir():
    adlar = {c.name for c in doctor.diagnose(live=False).checks}

    for beklenen in ("Fusion sürümü", "Python sürümü", "İşletim sistemi", "Yapılandırma dizini"):
        assert beklenen in adlar, f"{beklenen} kontrolü yok"


def test_yazilamayan_dizin_sorun_olarak_isaretlenir(monkeypatch, tmp_path):
    yasak = tmp_path / "yazilamaz"
    yasak.mkdir()
    yasak.chmod(0o500)
    monkeypatch.setattr(doctor, "memory_dir", lambda: yasak / "memory")

    rapor = doctor.diagnose(live=False)

    bellek = next(c for c in rapor.checks if "Bellek dizini" in c.name)
    assert bellek.ok is False
    yasak.chmod(0o700)


def test_canli_kontrol_varsayilan_kapali():
    rapor = doctor.diagnose(live=False)

    assert not any("canlı" in c.name.lower() for c in rapor.checks)


def test_canli_kontrol_tum_kademe_bas_modellerini_sondalar_ve_saglik_onbellegine_yazar(
    monkeypatch, tmp_path
):
    """`--live` yalnız üst düzey agent/judge'ı değil, HER kademenin baş modelini
    de sondalamalı ve sonucu `health_cache`'e yazmalı — model seçici bu diskten
    okur (bkz. `appserver/model_catalog.py::list_selectable_models`)."""
    from fusion_cli.config.loader import load_config
    from fusion_cli.core.types import ModelResult
    from fusion_cli.providers import health_cache, litellm_provider

    sondalanan: list[str] = []

    class SahteSaglayici:
        def __init__(self, model: str, *, role: str) -> None:
            self._model = model

        async def complete(self, request: object) -> ModelResult:
            sondalanan.append(self._model)
            basarili = "glm-5.3" not in self._model
            return ModelResult(
                name="sahte", model=self._model, text="pong" if basarili else "",
                latency_ms=10, ok=basarili, error=None if basarili else "zaman aşımı",
            )

    monkeypatch.setattr(litellm_provider, "LiteLlmProvider", SahteSaglayici)
    monkeypatch.setattr(litellm_provider, "configure_litellm", lambda: None)
    monkeypatch.setattr("fusion_cli.config.paths.user_data_dir", lambda: tmp_path)

    config = load_config()
    doctor.diagnose(live=True)

    beklenen_kademe_modelleri = {kademe.agent.models[0] for kademe in config.tiers}
    assert beklenen_kademe_modelleri <= set(sondalanan)

    onbellek = health_cache.load(tmp_path / health_cache.HEALTH_CACHE_FILENAME)
    assert onbellek[config.agent.models[0]].ok is True
    for model in beklenen_kademe_modelleri:
        assert model in onbellek
