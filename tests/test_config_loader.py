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


_WEB_OTURUMU_YAML = """
web_sessions:
- model: gemini_web/main/auto
  provider: gemini_web
  account: main
  transport: browser
  tool_support: emulated
  login_verified: true
  enabled: true
  selected_model: 3.6 Flash
"""


def test_profili_silinmis_web_oturumu_girisli_sayilmaz(monkeypatch, tmp_path):
    """Ölçüldü (11 Ekim, yeni Mac): veri dizini taşınmadı, config hâlâ
    `login_verified: true` diyordu; öğretmen girişsiz boş bir tarayıcıyla seçilip
    her danışmada zaman aşımına düşecekti."""
    from fusion_cli.config import loader

    yapilandirma = tmp_path / "config.yaml"
    yapilandirma.write_text(_WEB_OTURUMU_YAML, encoding="utf-8")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "veri"))

    sonuc = loader.load_config(yapilandirma)

    assert sonuc.web_sessions[0].login_verified is False
    assert sonuc.teacher is None


def test_profili_duran_web_oturumu_girisli_kalir(monkeypatch, tmp_path):
    from fusion_cli.config import loader
    from fusion_cli.config.paths import web_profile_dir

    yapilandirma = tmp_path / "config.yaml"
    yapilandirma.write_text(_WEB_OTURUMU_YAML, encoding="utf-8")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "veri"))
    web_profile_dir("gemini_web", "main").mkdir(parents=True)

    sonuc = loader.load_config(yapilandirma)

    assert sonuc.web_sessions[0].login_verified is True
    assert sonuc.teacher is not None and sonuc.teacher.model == "gemini_web/main/auto"


def test_profil_yolu_tarayici_katmaniyla_ayni():
    from fusion_cli.config.paths import web_profile_dir
    from fusion_cli.providers.web_browser import browser_profile_dir

    assert web_profile_dir("gemini_web", "Emirhan Hesap") == browser_profile_dir(
        "gemini_web", "Emirhan Hesap"
    )
