"""Cross-platform kullanıcı dizinleri ve yapılandırma dosyası çözümlemesi.

Windows: %APPDATA% / %LOCALAPPDATA%   ·   macOS & Linux: XDG (~/.config, ~/.local/share)

Global kurulumdan sonra `fusion` herhangi bir dizinde çalışır; ayarlar ve anahtarlar
bu kullanıcı dizinlerinden okunur.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from ..core.constants import KITS_STATE_FILENAME
from ..core.execution_context import PERSONAL_WORKSPACE, ExecutionContext, validate_identifier

APP_NAME = "fusion-cli"

#: Kullanıcı yapılandırmasının yolunu doğrudan belirleyen ortam değişkeni.
ENV_CONFIG = "FUSION_CONFIG"
#: Proje kökünü işaret eden, taşınabilir kurulumlar için kullanılan ortam değişkeni.
ENV_HOME = "FUSION_HOME"
#: Kalıcı belleğin yerini doğrudan belirleyen ortam değişkeni.
ENV_MEMORY_DIR = "FUSION_MEMORY_DIR"
#: Etkin yerel hesabın kimliği. Boşsa hesapsız (eski) düzen geçerlidir.
#
# Hesaplar aynı makineyi paylaşan kişilerin işlerini AYIRIR: hangi sağlayıcıya
# giriş yapıldığı, hangi MCP'lerin bağlı olduğu ve hangi modelin kullanıldığı
# hesaba özeldir. Ayrım TEK yerden yapılır — `user_config_dir` — çünkü bu
# bilgilerin tamamı `config.yaml`'da durur ve tüm okuyucular oradan geçer.
ENV_ACCOUNT = "FUSION_ACCOUNT"
#: "1" ise kalıcı veri (bellek, sır deposu, tarayıcı profilleri, kayıtlar) hesaba göre
#: ayrılır (WP02). Varsayılan KAPALI: açmadan önce eski ortak veri tek bir sahibe
#: bağlanmalıdır (`accounts.data_migration`); aksi hâlde hesap boş başlar.
ENV_WORKSPACE_ISOLATION = "FUSION_WORKSPACE_ISOLATION"
#: Hesaba göre ayrılmış veri köklerinin toplandığı alt klasör.
_TENANTS_DIR = "tenants"
#: Hesap dizinlerinin toplandığı alt klasör adı.
_ACCOUNTS_DIR = "accounts"


def active_account() -> str:
    """Etkin hesabın kimliği; hesapsız kullanımda boş metin."""
    return os.environ.get(ENV_ACCOUNT, "").strip()


def base_config_dir() -> Path:
    """Hesaptan BAĞIMSIZ yapılandırma kökü.

    Hesap listesi (`accounts.db`) buraya yazılır: hangi hesapların olduğunu
    bilmek için önce bir hesap seçmek gerekseydi giriş ekranı hiçbir şey
    listeleyemezdi.
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_NAME


def base_data_dir() -> Path:
    """Hesaptan BAĞIMSIZ kalıcı veri kökü."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_NAME


def kits_data_dir() -> Path:
    """Masaüstünün başlattığı Fusion Kits yan sürecinin veri klasörü.

    Tauri (`kits_process.rs`) aynı yolu `<veri kökü>/fusion-cli/kits` olarak kurar;
    hesaptan bağımsızdır çünkü Kits süreci uygulama başına tektir.
    """
    return base_data_dir() / "kits"


def kits_state_file() -> Path:
    """Kits'in adres+pid duyurduğu durum dosyası (`tools/kits.py` okur)."""
    return kits_data_dir() / KITS_STATE_FILENAME


def account_config_dir(account_id: str) -> Path:
    """Belirli bir hesabın yapılandırma dizini."""
    return base_config_dir() / _ACCOUNTS_DIR / account_id


def user_config_dir() -> Path:
    """`config.yaml` ve `.env` dosyalarının tutulduğu kullanıcı dizini.

    Hesap etkinse onun dizini döner; değilse eski düzen korunur. Hesabı olmayan
    bir kurulumun ayarları TAŞINMAZ — kullanıcı bir hesap açtığında dosyaları
    KOPYALAYARAK devralırız (bkz. `accounts.migration`).
    """
    account = active_account()
    return account_config_dir(account) if account else base_config_dir()


def workspace_isolation_enabled() -> bool:
    return os.environ.get(ENV_WORKSPACE_ISOLATION, "").strip() == "1"


def tenant_data_dir(tenant_id: str) -> Path:
    """Bir tenant'ın (pilotta: hesabın) veri kökü; kimlik yol kaçışı içeremez."""
    return base_data_dir() / _TENANTS_DIR / validate_identifier(tenant_id, "tenant")


def workspace_data_dir(context: ExecutionContext) -> Path:
    """Bağlamın yetkili veri kökü: başka tenant/workspace'in kökünü asla göstermez."""
    workspace = validate_identifier(context.workspace_id, "çalışma alanı")
    return tenant_data_dir(context.tenant_id) / workspace


def user_data_dir() -> Path:
    """Kalıcı verinin (bellek, sır deposu, tarayıcı profilleri, kayıtlar) kökü.

    Bayrak KAPALIYKEN hesaba göre değişmez (eski düzen). Ölçüldü (28 Ekim): bu düzende
    bellek, `secrets.enc` ve yerel ana anahtar, tarayıcı oturumları ve gönderim
    kayıtları bütün hesaplarda ORTAKTIR; hesap ayrımı yalnız `config.yaml`'daydı.
    `FUSION_WORKSPACE_ISOLATION=1` ile hesabın kendi köküne geçilir; eski veri
    oraya yalnız `accounts.data_migration` ile, seçilen TEK sahibe kopyalanır.
    """
    account = active_account()
    if account and workspace_isolation_enabled():
        # Bayrak açıkken: hesabın kişisel çalışma alanı (bkz. `workspace_data_dir`).
        return tenant_data_dir(account) / PERSONAL_WORKSPACE
    return base_data_dir()


def web_profile_dir(provider: str, account: str) -> Path:
    """Bir web sağlayıcı hesabının İZOLE tarayıcı profil dizini.

    Yol burada, `config` katmanında kurulur: yükleyici profilin diskte olup
    olmadığına bakarak `login_verified` bayrağını doğrular ve `providers`
    katmanına import edemez. Tarayıcı katmanı da aynı fonksiyonu kullanır.
    """
    return user_data_dir() / "web_profiles" / _slug(provider) / _slug(account)


def browser_profiles_dir() -> Path:
    """Ajan tarayıcısına (`browser_*`) taşınan kullanıcı oturumlarının kökü (P-023).

    `web_profiles/` ile karıştırılmaz: o dizin web MODEL sağlayıcılarının Chrome
    kullanıcı-veri dizinleridir; burası ad başına şifreli `storage_state` tutar.
    """
    return user_data_dir() / "browser_profiles"


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-._")
    return cleaned or "main"


def credentials_file() -> Path:
    """Şifreli sır deposunun dosya yolu (kalıcı veri dizini altında)."""
    if sys.platform == "darwin" and not os.environ.get("FUSION_SECRET_KEY", "").strip():
        return user_data_dir() / "vault" / "secrets.enc"
    return user_data_dir() / "secrets.enc"


def gallery_dir() -> Path:
    """Fusion'ın ürettiği görsellerin klasörü (uygulama içi galeri)."""
    return user_data_dir() / "gallery"


def capabilities_dir() -> Path:
    """`fusion yetenek kur` ile kurulan repoların yeri (skill/ajan keşfine dahil)."""
    return user_data_dir() / "yetenekler"


def trash_dir() -> Path:
    """Fusion çöpü: ajanın sildiği her şey buraya taşınır (bkz. `tools.safe_delete`)."""
    return user_data_dir() / "cop"


def memory_dir() -> Path:
    """Vektör belleğinin tutulduğu dizin. Ortam değişkeniyle taşınabilir."""
    override = os.environ.get(ENV_MEMORY_DIR)
    if override:
        return Path(override).expanduser()
    return user_data_dir() / "memory"


#: Kullanıcı düzenleyicisi bulunamazsa açılacak komut (macOS/Linux ve Windows).
_FALLBACK_EDITOR = "notepad" if sys.platform == "win32" else "nano"


def editor_command() -> tuple[str, ...]:
    """`/memory edit` gibi yerlerde dosya açacak düzenleyici: `VISUAL`, sonra `EDITOR`.

    Ortam erişimi yalnız bu katmanda yapılır (RULES). Değer boşluk içerebilir
    (`code --wait`); parçalanmış komut döner.
    """
    raw = os.environ.get("VISUAL") or os.environ.get("EDITOR") or _FALLBACK_EDITOR
    return tuple(raw.split()) or (_FALLBACK_EDITOR,)


def loop_dir() -> Path:
    """Kendini geliştirme döngüsünün kullanıcıya özel verisi (taslaklar, kullanıcı kümeleri,
    öneriler, istem sürümleri, ölçüm izi). Gerçek konuşmadan türer; makineden çıkmaz."""
    return user_data_dir() / "dongu"


def bundled_roster_dir() -> Path:
    """Pakete gömülü yerleşik ajan ekibi (kişilik dosyaları)."""
    return Path(__file__).resolve().parent / "roster"


def bundled_skills_dir() -> Path:
    """Pakete gömülü yerleşik beceriler (SKILL.md biçimi)."""
    return Path(__file__).resolve().parent / "skills"


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
