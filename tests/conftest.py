"""Tüm testler için ortak izolasyon.

Testler geliştiricinin KİŞİSEL yapılandırmasını okumamalı. `load_config()`
`~/.config/fusion-cli/config.yaml` dosyasını buluyordu; testler o makinedeki
ayara göre geçip kalıyordu.

Ölçüldü (2026-07-26): kişisel config'e `provider: nvidia` yazılınca dört test
kırıldı — kod hiç değişmemişti. Bu, testlerin yalan söylemesinin en sinsi
biçimidir: CI'da yeşil, geliştiricide kırmızı (ya da tersi).
"""

from __future__ import annotations

import gc

import pytest


@pytest.fixture(autouse=True)
def izole_kalici_bellek():
    """Testler arasında Chroma istemcilerinin dosya tanıtıcılarını bırak."""
    yield

    from fusion_cli.memory.store import reset_clients

    reset_clients()
    gc.collect()


@pytest.fixture(autouse=True)
def izole_kullanici_yapilandirmasi(monkeypatch, tmp_path):
    """Yalnızca pakete gömülü `defaults.yaml` kullanılsın.

    Ortam değişkenleriyle gelen override'lar da temizlenir: geliştiricinin
    kabuğunda `FUSION_CONFIG` tanımlıysa testler onu okurdu.
    """
    from fusion_cli.config import loader

    monkeypatch.setattr(loader, "user_config_candidates", tuple)
    for degisken in ("FUSION_CONFIG", "FUSION_HOME"):
        monkeypatch.delenv(degisken, raising=False)
    # AppSession konuşma dökümünü kalıcı belleğe yazar. Test turları gerçek
    # ~/.local/share/fusion-cli/memory geçmişine karışmamalıdır.
    # Keep the persistent-memory fixture outside the workspace root. Appserver
    # workspace tests intentionally inspect the complete project tree; placing
    # Chroma's files below ``tmp_path`` makes that host-only test dependency
    # look like user project content and also pollutes Git status.
    monkeypatch.setenv(
        "FUSION_MEMORY_DIR",
        str(tmp_path.parent / f".{tmp_path.name}-fusion-memory"),
    )


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
    monkeypatch.setattr(keys, "_local_master_key", lambda: None)
    monkeypatch.delenv(keys.FUSION_SECRET_ENV, raising=False)
