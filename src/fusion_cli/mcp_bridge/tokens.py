"""MCP OAuth sırlarını işletim sisteminin anahtarlığında sakla."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from collections.abc import Callable
from typing import ParamSpec, Protocol, TypeVar

from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import ValidationError

from ..core.errors import FusionError
from ..core.optional_read import OptionalReadWorker
from ..core.owned_thread import await_owned_thread

NONINTERACTIVE_READ_TIMEOUT_S = 1.0
_token_reader = OptionalReadWorker("fusion-mcp-credential-read")
_UNAVAILABLE = object()


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
    def __init__(self, *, interactive: bool = True) -> None:
        self._interactive = interactive

    def get_password(self, service: str, account: str) -> str | None:
        if not self._interactive and sys.platform == "darwin":
            from .keychain_read import read_password_noninteractive

            return read_password_noninteractive(service, account)
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

    def __init__(
        self, server_id: str, *, backend: KeyringBackend | None = None, interactive: bool = True
    ) -> None:
        digest = hashlib.sha256(server_id.encode("utf-8")).hexdigest()[:32]
        self._tokens_account = f"{digest}:tokens"
        self._client_account = f"{digest}:client"
        #: Önceden kayıtlı OAuth uygulamasının sırrı (Claude Code `--client-secret`, #248).
        self._secret_account = f"{digest}:secret"
        self._backend = backend or _SystemKeyring(interactive=interactive)
        self._interactive = interactive

    async def _read(self, account: str) -> str | None:
        if self._interactive:
            return await _keyring_call(self._backend.get_password, self._SERVICE, account)
        # Only reads use the daemon/no-queue helper. Mutations retain their
        # owned-thread completion and OAuth namespace ordering below.
        value = await _token_reader.run(
            lambda _valid: self._backend.get_password(self._SERVICE, account),
            timeout_s=NONINTERACTIVE_READ_TIMEOUT_S,
            fallback=_UNAVAILABLE,
            still_owned=lambda: True,
            wait_for_slot=True,
        )
        if value is not None and not isinstance(value, str):
            raise McpTokenStorageError(
                "Anahtarlık etkileşimsiz okunamadı; erişimi kontrol et ve açıkça yeniden bağlan."
            )
        return value

    async def get_tokens(self) -> OAuthToken | None:
        raw = await self._read(self._tokens_account)
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
        raw = await self._read(self._client_account)
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

    async def get_client_secret(self) -> str:
        raw = await self._read(self._secret_account)
        return raw or ""

    async def set_client_secret(self, secret: str) -> None:
        await _keyring_call(self._backend.set_password, self._SERVICE, self._secret_account, secret)

    async def clear(self, *, include_secret: bool = False) -> None:
        """Token ve istemci kaydını sil; `include_secret` sunucu kaldırılırken sırrı da siler."""
        accounts = (self._tokens_account, self._client_account)
        for account in (*accounts, *((self._secret_account,) if include_secret else ())):
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
