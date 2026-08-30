from __future__ import annotations

from email.message import Message
from urllib.error import HTTPError

from fusion_cli.appserver.web_preview import validate_web_preview


class _Response:
    def __init__(
        self,
        url: str,
        *,
        headers: dict[str, str] | list[tuple[str, str]] | None = None,
        status: int = 200,
    ):
        self._url = url
        self.headers = Message()
        records = headers.items() if isinstance(headers, dict) else headers or []
        for name, value in records:
            self.headers[name] = value
        self.status = status

    def geturl(self) -> str:
        return self._url

    def getcode(self) -> int:
        return self.status

    def close(self) -> None:
        return None


class _Opener:
    def __init__(self, response: _Response | Exception):
        self.response = response

    def open(self, _request, *, timeout: float):
        assert timeout <= 5
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_web_preview_yalniz_yerel_adresi_ve_yerel_son_hedefi_kabul_eder():
    external = validate_web_preview({"url": "https://example.com"})
    redirected = validate_web_preview(
        {"url": "http://localhost:5173"},
        opener=_Opener(_Response("https://example.com")),
    )

    assert external == {"ok": False, "metin": "Yalnız localhost adresleri önizlenebilir."}
    assert redirected == {"ok": False, "metin": "Yerel sunucu dış bir adrese yönlendirdi."}


def test_web_preview_gomulme_engelleyici_basliklari_acik_hatayla_reddeder():
    xfo = validate_web_preview(
        {"url": "http://127.0.0.1:4173"},
        opener=_Opener(_Response("http://127.0.0.1:4173", headers={"X-Frame-Options": "DENY"})),
    )
    csp = validate_web_preview(
        {"url": "http://[::1]:8080"},
        opener=_Opener(
            _Response(
                "http://[::1]:8080",
                headers={"Content-Security-Policy": "frame-ancestors 'none'"},
            )
        ),
    )

    assert xfo["ok"] is False
    assert "uygulama içine gömülmeyi engelliyor" in xfo["metin"]
    assert csp["ok"] is False
    assert "uygulama içine gömülmeyi engelliyor" in csp["metin"]


def test_web_preview_erisebilen_yerel_sunucuyu_dogrular():
    result = validate_web_preview(
        {"url": "http://localhost:5173/game"},
        opener=_Opener(_Response("http://localhost:5173/game", status=204)),
    )

    assert result == {"ok": True, "url": "http://localhost:5173/game", "durum": 204}


def test_web_preview_redirect_dongusunu_http_sayfasi_gibi_kabul_etmez():
    error = HTTPError(
        "http://localhost:5173/loop",
        302,
        "redirect loop",
        Message(),
        None,
    )
    result = validate_web_preview(
        {"url": "http://localhost:5173/loop"},
        opener=_Opener(error),
    )
    assert result == {"ok": False, "metin": "Yerel sunucunun yönlendirmesi tamamlanamadı."}


def test_web_preview_birden_fazla_csp_basliginin_tumunu_uygular():
    result = validate_web_preview(
        {"url": "http://localhost:5173"},
        opener=_Opener(
            _Response(
                "http://localhost:5173",
                headers=[
                    ("Content-Security-Policy", "frame-ancestors *"),
                    ("Content-Security-Policy", "frame-ancestors 'none'"),
                ],
            )
        ),
    )
    assert result["ok"] is False
    assert "CSP frame-ancestors" in result["metin"]
