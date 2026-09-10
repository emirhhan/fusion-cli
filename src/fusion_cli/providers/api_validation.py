"""Anahtar doğrulaması: sabit resmî uçlara kimlik doğrulamalı okuma isteği."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

TIMEOUT_SECONDS = 15
ENDPOINTS = {
    "openrouter": "https://openrouter.ai/api/v1/key",
    "openai": "https://api.openai.com/v1/models",
    "anthropic": "https://api.anthropic.com/v1/models",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models",
}


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    message: str


async def validate_api_key(
    provider: str, key: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> ValidationResult:
    """Anahtarın kabulünü sına; model üretimi/kota garantisi vermez."""
    endpoint = ENDPOINTS.get(provider)
    if endpoint is None:
        return ValidationResult(
            False, "Bu sağlayıcı için otomatik anahtar sınaması yok. Model seçip bağlantıyı dene."
        )
    if not key.strip():
        return ValidationResult(False, "Kayıtlı API anahtarı bulunamadı.")
    headers = {"Authorization": f"Bearer {key}"}
    if provider == "anthropic":
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    elif provider == "gemini":
        headers = {"x-goog-api-key": key}
    try:
        async with httpx.AsyncClient(
            timeout=TIMEOUT_SECONDS, follow_redirects=False, transport=transport
        ) as client:
            response = await client.get(endpoint, headers=headers)
    except httpx.HTTPError:
        return ValidationResult(
            False, "Sağlayıcıya ulaşılamadı. İnternet bağlantını kontrol edip tekrar dene."
        )
    if response.status_code in (401, 403):
        return ValidationResult(False, "API anahtarı reddedildi veya gerekli erişim izni yok.")
    if response.status_code == 429:
        return ValidationResult(
            False, "Sağlayıcının kullanım sınırına ulaşıldı. Daha sonra tekrar dene."
        )
    if response.status_code != 200:
        return ValidationResult(
            False, f"Sağlayıcı sınaması tamamlanamadı (HTTP {response.status_code})."
        )
    try:
        payload = response.json()
    except ValueError:
        return ValidationResult(False, "Sağlayıcı beklenen yanıtı vermedi.")
    expected = "models" if provider == "gemini" else "data"
    if not isinstance(payload, dict) or expected not in payload:
        return ValidationResult(False, "Sağlayıcı beklenen yanıtı vermedi.")
    return ValidationResult(
        True, "API anahtarı doğrulandı. Model kullanılabilirliği ve kota ayrıca geçerlidir."
    )
