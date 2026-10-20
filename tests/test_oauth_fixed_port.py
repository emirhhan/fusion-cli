"""Loopback OAuth callback adresi SABİT olmalı.

Ölçülmüş engel: Facebook Login, yönlendirme adresinin uygulama ayarlarındaki
kayıtla BİREBİR eşleşmesini ister. Dinleyici `port=0` ile açılıyordu, yani adres
her denemede `http://127.0.0.1:<rastgele>/oauth/callback` oluyordu ve hiçbir zaman
eşleşemezdi — kendi Meta uygulamasının client_id'siyle giriş bu yüzden imkânsızdı.
"""

from __future__ import annotations

import socket

import pytest

from fusion_cli.mcp_bridge.oauth import DEFAULT_CALLBACK_PORT, LoopbackOAuthCallback


async def test_varsayilan_adres_sabit_ve_localhost():
    """Adres tahmin edilebilir olmalı: kullanıcı Meta paneline bunu yapıştırır."""
    callback = LoopbackOAuthCallback()
    try:
        await callback.start()
        assert callback.redirect_uri == (f"http://localhost:{DEFAULT_CALLBACK_PORT}/oauth/callback")
    finally:
        await callback.close()


async def test_port_mesgulse_anlasilir_hata():
    """Sessizce başka porta kaymak, eşleşmeyen bir adresle giriş denemek olurdu."""
    blocker = socket.socket()
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    blocker.bind(("127.0.0.1", 0))
    port = blocker.getsockname()[1]
    blocker.listen(1)
    callback = LoopbackOAuthCallback(port=port)
    try:
        with pytest.raises(OSError, match=str(port)):
            await callback.start()
    finally:
        blocker.close()
        await callback.close()


async def test_sifir_port_hala_rastgele_secer():
    """DCR destekleyen sunucularda sabit port gereksiz; eski davranış korunur."""
    callback = LoopbackOAuthCallback(port=0)
    try:
        await callback.start()
        assert "/oauth/callback" in callback.redirect_uri
        assert f":{DEFAULT_CALLBACK_PORT}/" not in callback.redirect_uri
    finally:
        await callback.close()
