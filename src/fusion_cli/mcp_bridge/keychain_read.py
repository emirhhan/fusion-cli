"""macOS generic-password lookup with per-query authentication UI disabled.

Uses the installed keyring backend's native query/conversion primitives. No
process-wide interaction setting is changed. Missing and denied are distinct.
"""

from __future__ import annotations

import ctypes
from collections.abc import Callable
from typing import Protocol, cast


class KeychainReadUnavailableError(RuntimeError):
    """No native error text or credential value crosses this boundary."""


class _NativeApi(Protocol):
    def create_query(self, **kwargs: object) -> ctypes.c_void_p: ...
    def k_(self, name: str) -> ctypes.c_void_p: ...
    SecItemCopyMatching: Callable[[ctypes.c_void_p, object], int]
    def cfstr_to_str(self, data: ctypes.c_void_p) -> str: ...


def _copy_password(
    service: str, account: str, api: _NativeApi, release: Callable[[ctypes.c_void_p], None]
) -> str | None:
    query = api.create_query(
        kSecClass=api.k_("kSecClassGenericPassword"),
        kSecMatchLimit=api.k_("kSecMatchLimitOne"),
        kSecAttrService=service,
        kSecAttrAccount=account,
        kSecReturnData=True,
        kSecUseAuthenticationUI=api.k_("kSecUseAuthenticationUIFail"),
    )
    data = ctypes.c_void_p()
    try:
        status = api.SecItemCopyMatching(query, ctypes.byref(data))
        if status == -25300:  # errSecItemNotFound, never an access denial.
            return None
        if status != 0 or not data.value:
            raise KeychainReadUnavailableError("Anahtarlık etkileşimsiz okunamadı.")
        return str(api.cfstr_to_str(data))
    finally:
        if data.value:
            release(data)
        release(query)


def read_password_noninteractive(service: str, account: str) -> str | None:
    try:
        from keyring.backends.macOS import api

        core = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        core.CFRelease.argtypes = [ctypes.c_void_p]
        core.CFRelease.restype = None
        # ctypes function-pointer stubs cannot express the native call signature.
        return _copy_password(service, account, cast(_NativeApi, api), core.CFRelease)
    except Exception:
        # Native failures may include account details. Do not include their text.
        raise KeychainReadUnavailableError("Anahtarlık etkileşimsiz okunamadı.") from None
