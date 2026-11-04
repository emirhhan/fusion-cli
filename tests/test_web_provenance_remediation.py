"""Arama ve kaynak okumasının zaman/provenance sözleşmesi (ağsız)."""

from __future__ import annotations

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import web


class FixedClock:
    def now(self):
        return 1793750400.0

    def monotonic(self):
        return 0.0


def test_fetch_preserves_redirect_time_declared_dates_and_summary(monkeypatch, tmp_path):
    monkeypatch.setattr(web, "url_block_reason", lambda _url: None)
    monkeypatch.setattr(
        web,
        "fetch_following_redirects",
        lambda _url: (
            "text/html",
            '<html><meta property="article:published_time" content="2026-11-01">'
            '<meta property="article:modified_time" content="2026-11-03"><p>Veri: 42</p></html>',
            "https://final.test/article",
        ),
    )
    result = web.web_fetch(
        {"url": "https://source.test/start"}, ToolContext(root=tmp_path), clock=FixedClock()
    )
    source = result.structured["source"]
    assert source["url"] == "https://source.test/start"
    assert source["final_url"] == "https://final.test/article"
    assert source["fetched_at"] == "2026-11-04T00:00:00+00:00"
    assert source["published_at"] == "2026-11-01"
    assert source["updated_at"] == "2026-11-03"
    assert source["date_evidence"] == "page_metadata"
    assert "Veri: 42" in source["content_summary"]
    assert "https://final.test/article" in result.output
    assert "2026-11-04T00:00:00+00:00" in result.output


def test_html_search_retains_snippet_and_explicit_publication_date():
    html = (
        '<div class="result"><a class="result__a" href="https://source.test">Sürüm</a>'
        '<span class="result__timestamp">2026-11-02</span>'
        '<a class="result__snippet">Yeni sürümün <b>özellikleri</b>.</a></div>'
    )
    result = web.parse_anchor_results(html, "result__a")[0]
    assert "Yeni sürümün özellikleri." in result
    assert "2026-11-02" in result


def test_search_filter_and_search_time_are_observable(monkeypatch, tmp_path):
    seen = []

    def search(query, date_filter=""):
        seen.append((query, date_filter))
        return ["• Sürüm\n  https://source.test"]

    monkeypatch.setattr(web, "SEARCH_ENDPOINTS", (search,))
    result = web.web_search(
        {"query": "sürüm", "recency_days": 7}, ToolContext(root=tmp_path), clock=FixedClock()
    )
    assert seen == [("sürüm", "2026-10-28..2026-11-04")]
    assert result.structured["searched_at"] == "2026-11-04T00:00:00+00:00"
    assert result.structured["date_filter"] == "2026-10-28..2026-11-04"
    assert "Yayın tarihi bilinmiyor" in result.output


def test_search_rejects_invalid_filter_before_any_request(monkeypatch, tmp_path):
    def forbidden(*_args):
        raise AssertionError("geçersiz tarih ağa çıkmamalı")

    monkeypatch.setattr(web, "SEARCH_ENDPOINTS", (forbidden,))
    result = web.web_search(
        {"query": "sürüm", "date_from": "2026-99-99"},
        ToolContext(root=tmp_path),
        clock=FixedClock(),
    )
    assert not result.ok


def test_ddg_filter_is_transmitted_to_transport(monkeypatch):
    captured = []

    class Response:
        text = '<a class="result__a" href="https://source.test">Sürüm</a>'

        def raise_for_status(self):
            return None

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, url, *, data, headers):
            captured.append((url, data))
            return Response()

    monkeypatch.setattr(web.httpx, "Client", Client)
    results = web._search_html("sürüm", "2026-11-01..2026-11-04")
    assert results == ["• Sürüm\n  https://source.test"]
    assert captured == [
        ("https://html.duckduckgo.com/html/", {"q": "sürüm", "df": "2026-11-01..2026-11-04"})
    ]
    assert web._search_bing_rss("sürüm", "2026-11-01..2026-11-04") == []
    assert len(captured) == 1


def test_fetch_does_not_invent_publication_date_from_body(monkeypatch, tmp_path):
    monkeypatch.setattr(web, "url_block_reason", lambda _url: None)
    monkeypatch.setattr(
        web,
        "fetch_following_redirects",
        lambda url: (
            "text/html",
            "<html><p>2026-10-01 tarihinde başka ürün duyuruldu.</p></html>",
            url,
        ),
    )
    result = web.web_fetch(
        {"url": "https://source.test"}, ToolContext(root=tmp_path), clock=FixedClock()
    )
    assert result.structured["source"]["published_at"] is None
    assert result.structured["source"]["updated_at"] is None
    assert result.structured["source"]["date_evidence"] == "unknown"


def test_fetch_provenance_preserves_access_wall_protocol_prefix(tmp_path, monkeypatch):
    from fusion_cli.core.constants import CAPABILITY_WALL_PREFIX
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.tools import web

    monkeypatch.setattr(web, "url_block_reason", lambda _: None)
    monkeypatch.setattr(
        web,
        "fetch_following_redirects",
        lambda url: (
            "text/html",
            "<html><p>This store is password protected</p></html>",
            url,
        ),
    )
    result = web.web_fetch({"url": "https://shop.test"}, ToolContext(root=tmp_path))
    assert result.output.startswith(CAPABILITY_WALL_PREFIX)
    assert result.structured["source"]["final_url"] == "https://shop.test"
    assert result.structured["source"]["fetched_at"]
