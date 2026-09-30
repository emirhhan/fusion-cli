def test_acikca_verilen_fusion_config_yoksa_sessizce_baska_dosyaya_dusulmez(monkeypatch, tmp_path):
    """Ölçüldü: silinmiş geçici config'i gösteren FUSION_CONFIG sessizce kullanıcı
    config'ine düşüyor, tur beklenmeyen modelle çalışıyordu."""
    import pytest

    from fusion_cli.config.loader import load_config
    from fusion_cli.core.errors import ConfigError

    monkeypatch.setenv("FUSION_CONFIG", str(tmp_path / "yok.yaml"))
    with pytest.raises(ConfigError, match="bulunamadı"):
        load_config()


def test_env_dosyasindan_gelen_goreli_fusion_config_yoksa_yok_sayilir(monkeypatch, tmp_path):
    """Ölçüldü: kullanıcı `.env`'inde `FUSION_CONFIG=config.yaml` var; paket duman
    testi başka dizinde çalışınca katı kural çekirdeği hiç açılmaz hale getirdi."""
    import os

    from fusion_cli.config import loader

    monkeypatch.delenv("FUSION_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        loader, "load_environment", lambda: os.environ.__setitem__("FUSION_CONFIG", "config.yaml")
    )
    try:
        assert loader.load_config() is not None
    finally:
        os.environ.pop("FUSION_CONFIG", None)
