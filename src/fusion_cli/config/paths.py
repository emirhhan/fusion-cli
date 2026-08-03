"""Cross-platform kullanıcı dizinleri ve yapılandırma dosyası çözümlemesi.

Windows: %APPDATA% / %LOCALAPPDATA%   ·   macOS & Linux: XDG (~/.config, ~/.local/share)

Global kurulumdan sonra `fusion` herhangi bir dizinde çalışır; ayarlar ve anahtarlar
bu kullanıcı dizinlerinden okunur.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "fusion-cli"

#: Kullanıcı yapılandırmasının yolunu doğrudan belirleyen ortam değişkeni.
ENV_CONFIG = "FUSION_CONFIG"
#: Proje kökünü işaret eden, taşınabilir kurulumlar için kullanılan ortam değişkeni.
ENV_HOME = "FUSION_HOME"
#: Kalıcı belleğin yerini doğrudan belirleyen ortam değişkeni.
ENV_MEMORY_DIR = "FUSION_MEMORY_DIR"


def user_config_dir() -> Path:
    """`config.yaml` ve `.env` dosyalarının tutulduğu kullanıcı dizini."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_NAME


def user_data_dir() -> Path:
    """Kalıcı verinin (bellek, indeks, geçmiş) tutulduğu kullanıcı dizini."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_NAME
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_NAME


def credentials_file() -> Path:
    """Şifreli sır deposunun dosya yolu (kalıcı veri dizini altında)."""
    return user_data_dir() / "secrets.enc"


def memory_dir() -> Path:
    """Vektör belleğinin tutulduğu dizin. Ortam değişkeniyle taşınabilir."""
    override = os.environ.get(ENV_MEMORY_DIR)
    if override:
        return Path(override).expanduser()
    return user_data_dir() / "memory"


def bundled_defaults() -> Path:
    """Pakete gömülü `defaults.yaml`. Her zaman mevcuttur; varsayılanların tek kaynağıdır."""
    return Path(__file__).resolve().parent / "defaults.yaml"


def user_config_candidates() -> tuple[Path, ...]:
    """Kullanıcı yapılandırmasının aranacağı yollar, öncelik sırasıyla.

    İlk BULUNAN kullanılır; hiçbiri yoksa yalnızca gömülü varsayılanlar geçerlidir.
    """
    candidates: list[Path] = []
    from_env = os.environ.get(ENV_CONFIG)
    if from_env:
        candidates.append(Path(from_env))
    home = os.environ.get(ENV_HOME)
    if home:
        candidates.append(Path(home) / "config.yaml")
    # Kullanıcı yapılandırması terminal ve kontrol paneli süreçleri arasında
    # KANONİKtir: ikisi de aynı dosyayı görsün diye önce o gelir. Depo-yereli
    # config yalnızca taşınabilir geliştirme için bir yedek olarak kalır.
    candidates.append(user_config_dir() / "config.yaml")
    candidates.append(Path.cwd() / "config.yaml")
    return tuple(candidates)


def env_file_candidates() -> tuple[Path, ...]:
    """`.env` dosyasının aranacağı yollar, öncelik sırasıyla (ilk yüklenen kazanır)."""
    candidates: list[Path] = []
    home = os.environ.get(ENV_HOME)
    if home:
        candidates.append(Path(home) / ".env")
    candidates.append(Path.cwd() / ".env")
    candidates.append(user_config_dir() / ".env")
    return tuple(candidates)
