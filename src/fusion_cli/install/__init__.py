"""Kurulum yöntemi tespiti, PATH denetimi ve güncelleme/kaldırma yönlendirmesi.

Neden ayrı bir katman: aynı mantık `setup.sh` ve (gelecek) `install.ps1` içinde
iki kez yazılırsa zamanla ayrışır ve biri sessizce yanlış komut önerir. Scriptler
ince sarmalayıcı kalır, karar burada verilir.

Bu modül SAF'tır: hiçbir şey kurmaz, kaldırmaz, kullanıcının shell dosyasını
DEĞİŞTİRMEZ. Yalnızca durumu tespit eder ve çalıştırılacak komutu METİN olarak
üretir. Kullanıcının `.zshrc`'sini habersiz düzenlemek, kurulum betiğinin
yapabileceği en saldırgan şeydir.
"""

from __future__ import annotations

from .methods import (
    InstallMethod,
    detect_method,
    uninstall_command,
    update_command,
)
from .paths_check import path_hint

__all__ = [
    "InstallMethod",
    "detect_method",
    "path_hint",
    "uninstall_command",
    "update_command",
]
