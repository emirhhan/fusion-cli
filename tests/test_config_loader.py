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


def test_once_yuklenen_env_dosyasindaki_goreli_fusion_config_de_aday_sayilir(monkeypatch, tmp_path):
    """Ölçüldü (11 Ekim): `fusion doctor` önce `.env`'i yükleyip sonra `load_config`
    çağırıyor; `.env`'deki `FUSION_CONFIG=config.yaml` süreç ortamına girdiği için
    zorunlu sayıldı ve sağlam kurulum "hazır DEĞİL" göründü."""
    import os

    from fusion_cli.config import loader

    env_dosyasi = tmp_path / ".env"
    env_dosyasi.write_text("FUSION_CONFIG=config.yaml\n", encoding="utf-8")
    monkeypatch.delenv("FUSION_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(loader, "env_file_candidates", lambda: [env_dosyasi])
    monkeypatch.setattr(loader, "_apply_stored_secrets", lambda: None)
    monkeypatch.setattr(loader, "_DOTENV_KEYS", frozenset())
    try:
        loader.load_environment()
        assert loader.load_config() is not None
    finally:
        os.environ.pop("FUSION_CONFIG", None)
