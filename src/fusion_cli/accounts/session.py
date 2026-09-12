"""Etkin hesabın seçilmesi, hatırlanması ve ilk hesaba devir.

Hesap seçimi bir ORTAM DEĞİŞKENİNE yazılır (`FUSION_ACCOUNT`) çünkü yapılandırma
yolunu çözen katman (`config.paths`) saf kalmalı ve hesap deposunu import
etmemelidir — bağımlılık yönü `config → core` olmalı, tersi değil.

"Beni hatırla" da burada: seçim küçük bir işaretçi dosyada durur, böylece
uygulama yeniden açıldığında kullanıcı tekrar parola sormaz. Çıkış yapıldığında
dosya silinir.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from ..config.paths import ENV_ACCOUNT, account_config_dir, base_config_dir

__all__ = [
    "activate_account",
    "adopt_legacy_config",
    "clear_active_account",
    "forget_remembered_account",
    "remember_account",
    "remembered_account",
    "remove_account_files",
]

#: "Beni hatırla" işaretçisi. Hesap KİMLİĞİNDEN başka bir şey taşımaz; parola ya
#: da oturum jetonu içermez, çünkü doğrulama zaten yerel veritabanındadır.
_POINTER = "active-account"

#: İlk hesaba devredilen, hesaba özel yapılandırma dosyaları.
#
# Yalnız KÜÇÜK ve hesaba ait dosyalar kopyalanır. Tarayıcı profilleri ve bellek
# `user_data_dir` altındadır ve hesaba göre değişmez (bkz. `config.paths`).
_ADOPTED_FILES = ("config.yaml", ".env")


def activate_account(account_id: str) -> None:
    """Bu süreç için etkin hesabı ayarla ve dizininin var olduğundan emin ol.

    Dizin BURADA açılır çünkü etkinleştirme, yapılandırmanın o dizinden
    okunmaya/yazılmaya başladığı andır. Yalnız ilk hesapta (devralma sırasında)
    açılıyordu; ikinci hesap açan kullanıcı, var olmayan bir dizine yazmaya
    çalışan bir çekirdekle karşılaşırdı.
    """
    os.environ[ENV_ACCOUNT] = account_id
    if account_id:
        account_config_dir(account_id).mkdir(parents=True, exist_ok=True)


def clear_active_account() -> None:
    """Etkin hesabı bırak (çıkış)."""
    os.environ.pop(ENV_ACCOUNT, None)


def _pointer_path() -> Path:
    return base_config_dir() / _POINTER


def remember_account(account_id: str) -> None:
    """Seçimi kalıcılaştır: uygulama yeniden açıldığında parola sorulmaz."""
    yol = _pointer_path()
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(account_id, encoding="utf-8")


def forget_remembered_account() -> None:
    """Hatırlanan seçimi sil (çıkış)."""
    _pointer_path().unlink(missing_ok=True)


def remembered_account() -> str:
    """Hatırlanan hesabın kimliği; yoksa boş metin.

    Dosya okunamıyorsa HATA VERİLMEZ: en kötü ihtimalle kullanıcı bir kez daha
    giriş yapar, bu uygulamayı açılmaz yapmaktan iyidir.
    """
    try:
        return _pointer_path().read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def adopt_legacy_config(account_id: str) -> tuple[str, ...]:
    """Hesapsız kurulumun ayarlarını İLK hesaba kopyala; kopyalananları döndür.

    Kopyalanır, TAŞINMAZ: kullanıcının çalışan kurulumunu geri alınamaz biçimde
    değiştirmek, bir hesap açma işleminin yapmaması gereken bir şeydir. Eski
    dosyalar yerinde kalır ve hesaplı düzen beklendiği gibi çalışmazsa kullanıcı
    hiçbir şey kaybetmez.

    Hedefte aynı adlı dosya varsa DOKUNULMAZ: ikinci kez çağrılmak var olan bir
    hesabın ayarlarını ezmemelidir.
    """
    kaynak = base_config_dir()
    hedef = account_config_dir(account_id)
    hedef.mkdir(parents=True, exist_ok=True)
    kopyalanan: list[str] = []
    for ad in _ADOPTED_FILES:
        eski, yeni = kaynak / ad, hedef / ad
        if not eski.is_file() or yeni.exists():
            continue
        shutil.copy2(eski, yeni)
        kopyalanan.append(ad)
    return tuple(kopyalanan)


def remove_account_files(account_id: str) -> None:
    """Hesabın yapılandırma dizinini tamamen sil.

    Hesap silindiğinde ona ait ayarların kalması, silmenin anlamını boşa
    çıkarırdı. Silme yalnız HESAP DİZİNİNİ kapsar; paylaşılan veri dizinine
    (tarayıcı profilleri, bellek) dokunulmaz — orası başka hesaplara da aittir.
    """
    shutil.rmtree(account_config_dir(account_id), ignore_errors=True)
