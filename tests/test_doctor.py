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
    """"Başarısız" demek yetmez: kullanıcı ne çalıştıracağını bilmeli."""
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
