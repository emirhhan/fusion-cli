"""Genel OpenAI-uyumlu web-session transport'u.

`web_session.WebProviderAdapter` gerçek I/O'yu enjekte edilen bir `WebTransport`'a
bırakır. Bu modül, KULLANICININ SAHİP OLDUĞU / oturum erişimine İZİN VEREN bir
OpenAI-uyumlu uca (kendi OpenWebUI/LibreChat kurulumu, kurumsal uç…) bearer token,
cookie ve özel başlıklarla bağlanan somut bir transport üretir.

KAPSAM SINIRI: Belirli bir ticari tüketici web arayüzünü (ChatGPT/Gemini web) izinsiz
otomatikleştirmez; yalnızca kullanıcının yetkili olduğu bir HTTP ucuna standart bir
`/chat/completions` isteği atar. CAPTCHA/anti-bot aşımı ya da izinsiz cookie okuma yoktur.

Timeout koda gömülmez; `WEB_TIMEOUT_S` sabitinden gelir (bkz. core/constants).
"""

from __future__ import annotations

import httpx

from ..core.constants import WEB_TIMEOUT_S
from ..core.types import Message
from .web_session import WebSessionCredential, WebTransport


def build_http_transport(
    endpoint: str,
    *,
    http_transport: httpx.AsyncBaseTransport | None = None,
    timeout_s: float = WEB_TIMEOUT_S,
) -> WebTransport:
    """OpenAI-uyumlu bir uca istek atan bir `WebTransport` üret.

    `http_transport` yalnızca testte verilir (sahte httpx); üretimde None → gerçek ağ.
    Dönen fonksiyon `WebProviderAdapter`'a enjekte edilir ve onun sözleşmesine uyar:
    kimlik + mesajlar + model → yanıt metni; hata durumunda istisna fırlatır (adaptör
    onu `ok=False` sonuca çevirir).
    """

    async def _transport(
        credential: WebSessionCredential, messages: tuple[Message, ...], model: str
    ) -> str:
        headers = _headers(credential)
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        async with httpx.AsyncClient(
            transport=http_transport, timeout=timeout_s, cookies=dict(credential.cookies)
        ) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
        _raise_for_status(response)
        return _extract_text(response)

    return _transport


def _headers(credential: WebSessionCredential) -> dict[str, str]:
    """İstek başlıkları: özel başlıklar + (token varsa) Authorization."""
    headers = {"content-type": "application/json", **dict(credential.headers)}
    if credential.token:
        headers["authorization"] = f"Bearer {credential.token}"
    return headers


def _raise_for_status(response: httpx.Response) -> None:
    """Hata kodunda anlaşılır bir istisna fırlat (sağlayıcı açıklamasını da ekleyerek)."""
    if response.is_success:
        return
    detail = _error_message(response)
    raise httpx.HTTPStatusError(
        f"{response.status_code}: {detail}", request=response.request, response=response
    )


def _error_message(response: httpx.Response) -> str:
    """Yanıt gövdesindeki insan-okunur hata açıklamasını çıkar; yoksa ham metni kısalt."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str):
            return message
    return str(error or body)[:200]


def _extract_text(response: httpx.Response) -> str:
    """OpenAI-uyumlu yanıttan cevap metnini al; biçim beklenmedikse ham metne düş."""
    try:
        body = response.json()
        content = body["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        return response.text
    return str(content)
