"""MCP OAuth sırlarını işletim sisteminin anahtarlığında sakla."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable
from typing import ParamSpec, Protocol, TypeVar

from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import ValidationError

from ..core.errors import FusionError
from ..core.owned_thread import await_owned_thread


class McpTokenStorageError(FusionError):
    """Anahtarlık verisi veya erişimi güvenli bir hata ile bildirilir."""


_P = ParamSpec("_P")
_T = TypeVar("_T")


async def _keyring_call(operation: Callable[_P, _T], *args: _P.args, **kwargs: _P.kwargs) -> _T:
    """İptal OS thread'ini durdurmaz; yazım bitmeden namespace kilidini bırakma."""
    try:
        return await await_owned_thread(operation, *args, **kwargs)
    except asyncio.CancelledError:
        raise
    except Exception as error:
        raise McpTokenStorageError(
            f"Anahtarlık işlemi tamamlanamadı ({type(error).__name__}). Yeniden bağlan."
        ) from None


class KeyringBackend(Protocol):
    def get_password(self, service: str, account: str) -> str | None: ...
    def set_password(self, service: str, account: str, value: str) -> None: ...
    def delete_password(self, service: str, account: str) -> None: ...


class _SystemKeyring:
    def get_password(self, service: str, account: str) -> str | None:
        import keyring
        from keyring.errors import NoKeyringError

        # Anahtarlığı olmayan sistemde (başsız Linux, CI) kayıtlı token da yoktur.
        # Hata yükseltmek, kimlik doğrulama istemeyen HTTP MCP bağlantısını bile
        # tamamen düşürüyordu.
        try:
            return keyring.get_password(service, account)
        except NoKeyringError:
            return None

    def set_password(self, service: str, account: str, value: str) -> None:
        import keyring

        keyring.set_password(service, account, value)

    def delete_password(self, service: str, account: str) -> None:
        import keyring

        keyring.delete_password(service, account)


class KeyringTokenStorage:
    """MCP SDK TokenStorage sözleşmesinin Keychain/Secret Service karşılığı."""

    _SERVICE = "fusion-cli-mcp-oauth"

    def __init__(self, server_id: str, *, backend: KeyringBackend | None = None) -> None:
        digest = hashlib.sha256(server_id.encode("utf-8")).hexdigest()[:32]
        self._tokens_account = f"{digest}:tokens"
        self._client_account = f"{digest}:client"
        self._backend = backend or _SystemKeyring()

    async def get_tokens(self) -> OAuthToken | None:
        raw = await _keyring_call(self._backend.get_password, self._SERVICE, self._tokens_account)
        try:
            return OAuthToken.model_validate_json(raw) if raw else None
        except ValidationError:
            raise McpTokenStorageError(
                "MCP kimlik kaydı bozuk. Çıkış yapıp yeniden bağlan."
            ) from None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        await _keyring_call(
            self._backend.set_password,
            self._SERVICE,
            self._tokens_account,
            tokens.model_dump_json(),
        )

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        raw = await _keyring_call(self._backend.get_password, self._SERVICE, self._client_account)
        try:
            return OAuthClientInformationFull.model_validate_json(raw) if raw else None
        except ValidationError:
            raise McpTokenStorageError(
                "MCP istemci kaydı bozuk. Çıkış yapıp yeniden bağlan."
            ) from None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        await _keyring_call(
            self._backend.set_password,
            self._SERVICE,
            self._client_account,
            client_info.model_dump_json(),
        )

    async def clear(self) -> None:
        for account in (self._tokens_account, self._client_account):
            try:
                await _keyring_call(self._backend.delete_password, self._SERVICE, account)
            except Exception:
                # Keyring arka uçları bulunmayan kaydı farklı istisnalarla bildirir.
                if (
                    await _keyring_call(self._backend.get_password, self._SERVICE, account)
                    is not None
                ):
                    raise

    def debug_identity(self) -> str:
        """Tanılama için sır içermeyen kararlı depo kimliği."""
        return json.dumps({"service": self._SERVICE, "account": self._tokens_account})
