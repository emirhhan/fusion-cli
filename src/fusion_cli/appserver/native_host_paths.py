"""Chromium tabanlı tarayıcıların yerel mesajlaşma (native messaging) kayıt yerleri (#433).

Claude Code: Google Chrome ve Microsoft Edge desteklenir; Brave, Arc, Vivaldi, Opera da
algılanıp bağlanır. Bildirim dosyası her tarayıcının kendi `NativeMessagingHosts` dizinine
(macOS, Linux) ya da kayıt defteri anahtarına (Windows) yazılır. Yalnız kurulu (veri dizini
olan) tarayıcılara yazılır; WSL desteklenmez.
"""

from __future__ import annotations

from pathlib import Path

#: macOS: `~/Library/Application Support/<veri dizini>/NativeMessagingHosts`.
MAC_BROWSER_DIRS: tuple[tuple[str, str], ...] = (
    ("Google Chrome", "Google/Chrome"),
    ("Chromium", "Chromium"),
    ("Microsoft Edge", "Microsoft Edge"),
    ("Brave", "BraveSoftware/Brave-Browser"),
    ("Arc", "Arc/User Data"),
    ("Vivaldi", "Vivaldi"),
    ("Opera", "com.operasoftware.Opera"),
)
#: Linux: `~/.config/<veri dizini>/NativeMessagingHosts`.
LINUX_BROWSER_DIRS: tuple[tuple[str, str], ...] = (
    ("Google Chrome", "google-chrome"),
    ("Chromium", "chromium"),
    ("Microsoft Edge", "microsoft-edge"),
    ("Brave", "BraveSoftware/Brave-Browser"),
    ("Vivaldi", "vivaldi"),
    ("Opera", "opera"),
)
#: Windows: HKCU altında `<anahtar>\\NativeMessagingHosts\\<host>`.
WINDOWS_BROWSER_KEYS: tuple[tuple[str, str], ...] = (
    ("Google Chrome", r"Software\Google\Chrome"),
    ("Chromium", r"Software\Chromium"),
    ("Microsoft Edge", r"Software\Microsoft\Edge"),
    ("Brave", r"Software\BraveSoftware\Brave-Browser"),
    ("Vivaldi", r"Software\Vivaldi"),
    ("Opera", r"Software\Opera Software"),
)


def host_dirs(home: Path, platform: str) -> list[Path]:
    """Platformun tüm tarayıcı `NativeMessagingHosts` dizinleri (kurulu olup olmadığına bakmaz)."""
    if platform == "darwin":
        base = home / "Library" / "Application Support"
        return [base / data / "NativeMessagingHosts" for _name, data in MAC_BROWSER_DIRS]
    if platform.startswith("linux"):
        base = home / ".config"
        return [base / data / "NativeMessagingHosts" for _name, data in LINUX_BROWSER_DIRS]
    return []


def windows_host_keys(host_name: str) -> list[str]:
    """Windows kayıt defteri anahtarları (HKCU)."""
    return [rf"{key}\NativeMessagingHosts\{host_name}" for _name, key in WINDOWS_BROWSER_KEYS]
