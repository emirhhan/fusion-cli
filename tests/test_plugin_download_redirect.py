"""Eklenti archive / `.mcpb` indirmelerinde yönlendirme denetimi (#399, #400).

Her yönlendirme adımı `archive_url_allowed` ile yeniden denetlenir; başka ana makineye giden
adımda girdinin `headers`/`headersHelper` başlıkları (Authorization dahil) taşınmaz.
"""

from __future__ import annotations

import io
import urllib.request
import urllib.response
from email import message_from_string
from http.client import HTTPMessage

import pytest

from fusion_cli.config import plugin_mcpb
from fusion_cli.config.plugin_archive import CheckedRedirect
from fusion_cli.core.plugins import PluginError


def _redirect(url: str, headers: dict[str, str], target: str) -> urllib.request.Request | None:
    request = urllib.request.Request(url, headers={"User-Agent": "fusion-cli", **headers})
    return CheckedRedirect().redirect_request(
        request, io.BytesIO(), 302, "Found", HTTPMessage(), target
    )


def test_baska_ana_makineye_yonlendirmede_kimlik_basliklari_dusurulur():
    new = _redirect(
        "https://a.example/x.zip",
        {"Authorization": "Bearer gizli", "X-Token": "t"},
        "https://cdn.example/x.zip",
    )

    assert new is not None
    names = {key.lower() for key in new.header_items() for key in [key[0]]}
    assert names == {"user-agent"}


def test_ayni_ana_makinede_basliklar_korunur():
    new = _redirect("https://a.example/x.zip", {"Authorization": "Bearer g"}, "https://a.example/y")

    assert new is not None and new.get_header("Authorization") == "Bearer g"


@pytest.mark.parametrize(
    "target", ["https://127.0.0.1/x", "https://169.254.169.254/latest", "http://a.example/x"]
)
def test_izin_verilmeyen_adrese_yonlendirme_reddedilir(target):
    with pytest.raises(PluginError, match="yönlendirme"):
        _redirect("https://a.example/x.zip", {}, target)


class _Sahte302(urllib.request.HTTPSHandler):
    """Genel sunucu 302 ile meta veri adresine yönlendirir; izlenirse test düşer."""

    def https_open(self, req):
        if "genel.example" in req.full_url:
            headers = message_from_string(
                "Location: https://169.254.169.254/latest\r\n\r\n", _class=HTTPMessage
            )
            response = urllib.response.addinfourl(io.BytesIO(b""), headers, req.full_url, 302)
            response.msg = "Found"
            return response
        raise AssertionError(f"yönlendirme izlendi: {req.full_url}")


def test_mcpb_indirmesi_yonlendirmeyi_denetler(monkeypatch):
    monkeypatch.setattr(urllib.request, "HTTPSHandler", _Sahte302)

    with pytest.raises(PluginError, match="yönlendirme"):
        plugin_mcpb._download("https://genel.example/paket.mcpb", "rapor")
