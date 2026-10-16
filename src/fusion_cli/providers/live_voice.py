"""Doğrudan ses modeli için anahtarı sunucuda tutan WebRTC bağlantı adaptörü."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files

import httpx


@dataclass(frozen=True)
class LiveVoiceOffer:
    """İstemciye yalnız bağlantı yanıtı veya güvenli hata gider."""

    ok: bool
    message: str = ""
    session_id: str = ""
    sdp: str = ""


class LiveVoiceProvider:
    """Ücretli oturum yalnız açık kabul ve geçerli teklif ile oluşturulur."""

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def connect(self, sdp: object, key: str, *, consent: bool) -> LiveVoiceOffer:
        """İstemci delegasyonu Fusion'da kalır; arayüz API anahtarını almaz."""
        if not consent:
            return LiveVoiceOffer(False, "Canlı ses için API ücretlendirmesini kabul etmelisin.")
        if not key.strip():
            return LiveVoiceOffer(
                False,
                "Canlı ses için Ayarlar → Sağlayıcılar bölümüne OpenAI API anahtarı ekle. "
                "ChatGPT aboneliği API erişimi sağlamaz.",
            )
        config = json.loads(
            files("fusion_cli.providers").joinpath("data/live-voice.json").read_text()
        )
        if (
            not isinstance(sdp, str)
            or not sdp.startswith("v=0")
            or len(sdp) > config["max_offer_chars"]
        ):
            return LiveVoiceOffer(
                False, "Mikrofon bağlantı teklifi geçersiz. Konuşmayı yeniden aç."
            )
        try:
            async with httpx.AsyncClient(
                timeout=config["timeout_seconds"], transport=self._transport, follow_redirects=False
            ) as client:
                response = await client.post(
                    config["endpoint"],
                    headers={"Authorization": f"Bearer {key}"},
                    json={
                        "session": config["session"],
                        "transport": {"type": "webrtc", "sdp": sdp},
                    },
                )
        except httpx.HTTPError:
            return LiveVoiceOffer(
                False,
                "Canlı ses sağlayıcısına ulaşılamadı. "
                "Bağlantını kontrol et; yerel ses kullanılabilir.",
            )
        if response.status_code in (401, 403):
            return LiveVoiceOffer(
                False,
                "OpenAI anahtarı veya canlı ses modeline erişim reddedildi. "
                "API hesabını kontrol et.",
            )
        if response.status_code == 429:
            return LiveVoiceOffer(
                False, "Canlı ses kotası veya API bakiyesi yetersiz. Sağlayıcı hesabını kontrol et."
            )
        if response.status_code != 201:
            return LiveVoiceOffer(
                False, f"Canlı ses oturumu açılamadı (HTTP {response.status_code})."
            )
        try:
            payload = response.json()
            session_id = payload["session"]["id"]
            answer = payload["transport"]["sdp"]
            if (
                not isinstance(session_id, str)
                or not session_id
                or not isinstance(answer, str)
                or not answer.startswith("v=0")
            ):
                raise ValueError("Bağlantı yanıtı geçersiz")
        except (ValueError, KeyError, TypeError):
            return LiveVoiceOffer(False, "Canlı ses sağlayıcısı geçerli bağlantı yanıtı vermedi.")
        return LiveVoiceOffer(True, session_id=session_id, sdp=answer)
