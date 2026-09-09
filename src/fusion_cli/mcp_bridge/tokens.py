"""MCP OAuth sırlarını işletim sisteminin anahtarlığında sakla."""

from __future__ import annotations

import hashlib
import json
from typing import Protocol

from mcp.shared.auth import OAuthClientInformationFull, OAuthToken


class KeyringBackend(Protocol):
    def get_password(self, service: str, account: str) -> str | None: ...
    def set_password(self, service: str, account: str, value: str) -> None: ...
    def delete_password(self, service: str, account: str) -> None: ...


class _SystemKeyring:
    def get_password(self, service: str, account: str) -> str | None:
        import keyring

        return keyring.get_password(service, account)

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
        raw = self._backend.get_password(self._SERVICE, self._tokens_account)
        return OAuthToken.model_validate_json(raw) if raw else None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self._backend.set_password(self._SERVICE, self._tokens_account, tokens.model_dump_json())

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        raw = self._backend.get_password(self._SERVICE, self._client_account)
        return OAuthClientInformationFull.model_validate_json(raw) if raw else None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self._backend.set_password(
            self._SERVICE, self._client_account, client_info.model_dump_json()
        )

    async def clear(self) -> None:
        for account in (self._tokens_account, self._client_account):
            try:
                self._backend.delete_password(self._SERVICE, account)
            except Exception:
                # Keyring arka uçları bulunmayan kaydı farklı istisnalarla bildirir.
                if self._backend.get_password(self._SERVICE, account) is not None:
                    raise

    def debug_identity(self) -> str:
        """Tanılama için sır içermeyen kararlı depo kimliği."""
        return json.dumps({"service": self._SERVICE, "account": self._tokens_account})
