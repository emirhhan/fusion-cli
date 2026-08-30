"""Yerel web önizlemesini iframe'e vermeden önce güvenli ve gömülebilir doğrula."""

from __future__ import annotations

from http.client import HTTPMessage
from typing import IO, Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class PreviewValidationError(RuntimeError):
    """Kullanıcıya gösterilebilen yerel önizleme doğrulama hatası."""


class _Response(Protocol):
    headers: HTTPMessage

    def geturl(self) -> str: ...

    def getcode(self) -> int: ...

    def close(self) -> None: ...


class _Opener(Protocol):
    def open(self, request: Request, *, timeout: float) -> _Response: ...


def is_local_preview_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlparse(value)
        return parsed.scheme == "http" and parsed.hostname in _LOCAL_HOSTS
    except ValueError:
        return False


class _LocalRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> Request | None:
        if not is_local_preview_url(newurl):
            raise PreviewValidationError("Yerel sunucu dış bir adrese yönlendirdi.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _embedding_error(headers: HTTPMessage) -> str | None:
    x_frame_options = str(headers.get("X-Frame-Options", "")).strip().casefold()
    if x_frame_options and x_frame_options != "allowall":
        return "Yerel sunucu uygulama içine gömülmeyi engelliyor (X-Frame-Options)."

    for csp in headers.get_all("Content-Security-Policy", []):
        for directive in csp.split(";"):
            name, _, value = directive.strip().partition(" ")
            if name.casefold() != "frame-ancestors":
                continue
            allowed = value.casefold().split()
            if "*" not in allowed and not any(
                origin in allowed
                for origin in ("tauri:", "http://tauri.localhost", "https://tauri.localhost")
            ):
                return "Yerel sunucu uygulama içine gömülmeyi engelliyor (CSP frame-ancestors)."
    return None


def _result_from_response(response: _Response) -> dict[str, Any]:
    final_url = response.geturl()
    if not is_local_preview_url(final_url):
        return {"ok": False, "metin": "Yerel sunucu dış bir adrese yönlendirdi."}
    if blocker := _embedding_error(response.headers):
        return {"ok": False, "metin": blocker}
    return {
        "ok": True,
        "url": final_url,
        "durum": int(response.getcode()),
    }


def validate_web_preview(
    data: dict[str, Any],
    *,
    opener: _Opener | None = None,
    timeout: float = 3.0,
) -> dict[str, Any]:
    """Adresi yerel ağ sınırında tut, erişimi ve iframe başlıklarını doğrula."""

    url = data.get("url")
    if not is_local_preview_url(url):
        return {"ok": False, "metin": "Yalnız localhost adresleri önizlenebilir."}
    request = Request(str(url), headers={"User-Agent": "Fusion-Preview/1"})
    client = opener or cast(_Opener, build_opener(_LocalRedirectHandler()))
    try:
        response = client.open(request, timeout=timeout)
        try:
            return _result_from_response(response)
        finally:
            response.close()
    except HTTPError as response:
        if 300 <= response.code < 400:
            return {"ok": False, "metin": "Yerel sunucunun yönlendirmesi tamamlanamadı."}
        # 4xx/5xx yanıtları da tarayıcıda anlamlı bir sayfa olabilir; güvenlik
        # başlıklarını ve nihai adresi yine denetleyerek önizlemeye izin ver.
        return _result_from_response(cast(_Response, response))
    except PreviewValidationError as error:
        return {"ok": False, "metin": str(error)}
    except TimeoutError:
        return {"ok": False, "metin": "Yerel sunucu zamanında yanıt vermedi."}
    except (URLError, OSError):
        return {"ok": False, "metin": "Yerel sunucuya bağlanılamadı."}
