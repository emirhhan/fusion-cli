"""Yerel hesaplar — kayıt, giriş, hesap başına yapılandırma.

Hesaplar kullanıcının kendi bilgisayarındadır; sunucu yoktur. Katman `core` ve
`config` üzerine kurulur, üst katmanları import etmez.
"""

from .avatars import AVATAR_MAX_BYTES, AVATAR_SUFFIXES, is_image_avatar, store_avatar_image
from .passwords import PASSWORD_MIN_CHARS, format_recovery_code, normalize_recovery_code
from .session import (
    activate_account,
    adopt_legacy_config,
    clear_active_account,
    forget_remembered_account,
    remember_account,
    remembered_account,
    remove_account_files,
)
from .store import AccountError, SqliteAccountStore, accounts_db_path

__all__ = [
    "AVATAR_MAX_BYTES",
    "AVATAR_SUFFIXES",
    "PASSWORD_MIN_CHARS",
    "AccountError",
    "SqliteAccountStore",
    "accounts_db_path",
    "activate_account",
    "adopt_legacy_config",
    "clear_active_account",
    "forget_remembered_account",
    "format_recovery_code",
    "is_image_avatar",
    "normalize_recovery_code",
    "remember_account",
    "remembered_account",
    "remove_account_files",
    "store_avatar_image",
]
