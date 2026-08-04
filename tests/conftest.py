"""Tüm testler için ortak izolasyon.

Testler geliştiricinin KİŞİSEL yapılandırmasını okumamalı. `load_config()`
`~/.config/fusion-cli/config.yaml` dosyasını buluyordu; testler o makinedeki
ayara göre geçip kalıyordu.

Ölçüldü (2026-07-26): kişisel config'e `provider: nvidia` yazılınca dört test
kırıldı — kod hiç değişmemişti. Bu, testlerin yalan söylemesinin en sinsi
biçimidir: CI'da yeşil, geliştiricide kırmızı (ya da tersi).
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def izole_kullanici_yapilandirmasi(monkeypatch):
    """Yalnızca pakete gömülü `defaults.yaml` kullanılsın.

    Ortam değişkenleriyle gelen override'lar da temizlenir: geliştiricinin
    kabuğunda `FUSION_CONFIG` tanımlıysa testler onu okurdu.
    """
    from fusion_cli.config import loader

    monkeypatch.setattr(loader, "user_config_candidates", tuple)
    for degisken in ("FUSION_CONFIG", "FUSION_HOME"):
        monkeypatch.delenv(degisken, raising=False)


@pytest.fixture(autouse=True)
def izole_sistem_anahtarligi(monkeypatch):
    """Hiçbir test gerçek sistem anahtarlığına (macOS Keychain vb.) dokunmasın.

    `GatewayApp` store verilmeden kurulunca `_default_secret_store` → `secret_key`
    → `_keyring_master_key` gerçek keychain'e gidip master key'i YAZMAYA çalışıyordu.
    Bu, geliştiricinin login keychain'ine yan etki bırakıyor ve GUI olmayan süreçte
    "saklanacağı anahtar zinciri bulunamadı" hatasını kullanıcının ekranına düşürüyordu.
    Anahtarı açıkça veren testler (`FernetSecretStore(secret_key=...)`) etkilenmez.
    """
    from fusion_cli.config import keys

    monkeypatch.setattr(keys, "_keyring_master_key", lambda: None)
    monkeypatch.delenv(keys.FUSION_SECRET_ENV, raising=False)
