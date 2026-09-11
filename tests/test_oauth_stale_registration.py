"""Yönlendirme adresi değişince eski istemci kaydı atılmalı.

Ölçüldü (11 Eylül, Notion MCP): kullanıcı bağlanmayı denedi ve Notion
`Invalid redirect_uri for OAuth client` döndürdü. Sebep: istemci DAHA ÖNCE
rastgele portlu bir adresle (`http://127.0.0.1:<rastgele>/oauth/callback`)
kaydolmuştu ve o kayıt anahtarlıkta duruyordu. Port sabitlendikten sonra
(`DEFAULT_CALLBACK_PORT`) yetkilendirme isteği yeni adresi gönderiyor, sunucu ise
kayıtlı adresi bekliyor ve reddediyor.

Kayıt, kaydedildiği yönlendirme adresine BAĞLIDIR. Adres değiştiyse kayıt
bayatlamıştır; saklamak kullanıcıyı çözemeyeceği bir hataya kilitler.
"""

from __future__ import annotations

from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

from fusion_cli.mcp_bridge.oauth import registration_is_stale


def _client(*redirects: str) -> OAuthClientInformationFull:
    return OAuthClientInformationFull(
        client_id="kayitli-id",
        redirect_uris=[AnyUrl(item) for item in redirects],
    )


def test_eski_portlu_kayit_bayat_sayilir():
    kayit = _client("http://127.0.0.1:51234/oauth/callback")

    assert registration_is_stale(kayit, "http://localhost:8765/oauth/callback") is True


def test_ayni_adresli_kayit_korunur():
    adres = "http://localhost:8765/oauth/callback"

    assert registration_is_stale(_client(adres), adres) is False


def test_birden_cok_adresten_biri_esleserse_korunur():
    """Sunucu birden çok adres kaydetmiş olabilir; biri yeterlidir."""
    kayit = _client("http://localhost:9999/oauth/callback", "http://localhost:8765/oauth/callback")

    assert registration_is_stale(kayit, "http://localhost:8765/oauth/callback") is False


def test_kayit_yoksa_bayatlik_sorusu_sorulmaz():
    assert registration_is_stale(None, "http://localhost:8765/oauth/callback") is False
