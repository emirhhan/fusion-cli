

def test_acikca_verilen_fusion_config_yoksa_sessizce_baska_dosyaya_dusulmez(monkeypatch, tmp_path):
    """Ölçüldü: silinmiş geçici config'i gösteren FUSION_CONFIG sessizce kullanıcı
    config'ine düşüyor, tur beklenmeyen modelle çalışıyordu."""
    import pytest

    from fusion_cli.config.loader import load_config
    from fusion_cli.core.errors import ConfigError

    monkeypatch.setenv("FUSION_CONFIG", str(tmp_path / "yok.yaml"))
    with pytest.raises(ConfigError, match="bulunamadı"):
        load_config()
