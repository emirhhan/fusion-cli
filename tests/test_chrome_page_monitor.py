"""Eklentinin sayfa izleyicisi (`pageMonitor.js`) ve okuyucusu (`readMonitor`) GERÇEK Chromium'da.

Konsol iletileri, hata olayları, `fetch`/XHR istekleri ve yanıt gövdesi `debugger` izni
olmadan sayfa içinde toplanır (P-042). Playwright Chromium'u kurulu değilse atlanır.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

playwright_sync = pytest.importorskip("playwright.sync_api")

EXTENSION = Path(__file__).resolve().parents[1] / "chrome-extension"


def _read_monitor_source() -> str:
    core = (EXTENSION / "core.js").read_text(encoding="utf-8")
    match = re.search(r"export function readMonitor\(args\) \{.*?\n\}\n", core, re.S)
    assert match, "readMonitor core.js içinde bulunamadı"
    return match.group(0).removeprefix("export ")


def _monitor_state_source() -> str:
    core = (EXTENSION / "core.js").read_text(encoding="utf-8")
    match = re.search(r"export function monitorState\(\) \{.*?\n\}\n", core, re.S)
    assert match
    return match.group(0).removeprefix("export ")


_SAYFA = """
<!doctype html><html><head><meta charset="utf-8"><title>İzleme</title></head>
<body><button id="go">Çağır</button>
<script>
  console.log("sayfa açıldı", {adim: 1});
  console.warn("uyarı");
  console.error("TypeError: beklenmeyen");
  document.getElementById("go").addEventListener("click", async () => {
    const yanit = await fetch("/api/urunler?token=gizli123", { method: "POST", body: "{}" });
    window.__sonuc = await yanit.json();
    const xhr = new XMLHttpRequest();
    xhr.open("GET", "/api/metin");
    xhr.send();
    fetch("/api/yok").catch(() => {});
    setTimeout(() => { throw new Error("gecikmeli hata"); }, 0);
  });
</script></body></html>
"""


@pytest.fixture(scope="module")
def tarayici():
    with playwright_sync.sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Exception as error:  # Chromium ikilisi kurulu değil
            pytest.skip(f"Playwright Chromium başlatılamadı: {error}")
        yield browser
        browser.close()


@pytest.fixture
def sayfa(tarayici):
    page = tarayici.new_page()
    # Eklenti izleyiciyi `document_start`ta ANA dünyaya ekler; init script aynı anı verir.
    page.add_init_script(path=str(EXTENSION / "pageMonitor.js"))

    def _karsila(route):
        url = route.request.url
        if url.endswith("/api/metin"):
            route.fulfill(body="düz metin yanıt", content_type="text/plain; charset=utf-8")
        elif "/api/urunler" in url:
            route.fulfill(body=json.dumps({"adet": 3}), content_type="application/json")
        elif url.endswith("/api/yok"):
            route.fulfill(status=500, body="hata", content_type="text/plain")
        else:
            route.fulfill(body=_SAYFA, content_type="text/html; charset=utf-8")

    page.route("http://izle.test/**", _karsila)
    page.goto("http://izle.test/")
    okuyucu = _read_monitor_source()
    durum = _monitor_state_source()
    page.oku = lambda args: page.evaluate(f"(a) => ({okuyucu})(a)", args)
    page.durum = lambda: page.evaluate(f"() => ({durum})()")
    yield page
    page.close()


def test_konsol_iletileri_yuklenirken_bile_yakalanir_ve_filtrelenir(sayfa):
    hepsi = sayfa.oku({"kind": "console"})
    hatalar = sayfa.oku({"kind": "console", "only_errors": True})
    desen = sayfa.oku({"kind": "console", "pattern": "typeerror"})

    assert hepsi["present"] is True and hepsi["total"] == 3
    assert [m["level"] for m in hepsi["messages"]] == ["log", "warn", "error"]
    assert hepsi["messages"][0]["text"] == 'sayfa açıldı {"adim":1}'
    assert [m["text"] for m in hatalar["messages"]] == ["TypeError: beklenmeyen"]
    assert desen["matched"] == 1
    # Sayfanın kendi console'u çalışmaya devam eder (sarmalama özgün işlevi çağırır).
    assert sayfa.evaluate("typeof console.log") == "function"


def test_fetch_ve_xhr_istekleri_durum_tur_sure_ve_govdeyle_kaydedilir(sayfa):
    sayfa.click("#go")
    sayfa.wait_for_function("window.__sonuc && window.__sonuc.adet === 3")
    sayfa.wait_for_function("globalThis.__fusionMonitor.pending === 0")
    sayfa.wait_for_function(
        "globalThis.__fusionMonitor.console.some(m => m.text.includes('gecikmeli'))"
    )

    ag = sayfa.oku({"kind": "network"})
    istek = next(r for r in ag["requests"] if "/api/urunler" in r["url"])
    metin = next(r for r in ag["requests"] if r["url"].endswith("/api/metin"))
    hata = next(r for r in ag["requests"] if r["url"].endswith("/api/yok"))

    assert ag["present"] and ag["pending"] == 0 and ag["total"] == 3
    assert istek["method"] == "POST" and istek["status"] == 200 and istek["kind"] == "fetch"
    assert istek["type"] == "application/json" and istek["has_body"] is True
    assert "body" not in istek, "liste gövde taşımaz; gövde request_id ile okunur"
    assert isinstance(istek["ms"], int)
    assert metin["kind"] == "xhr" and metin["status"] == 200 and metin["has_body"] is True
    assert hata["status"] == 500

    govde = sayfa.oku({"kind": "network", "request_id": istek["id"]})
    assert govde["request"]["body"] == '{"adet": 3}'
    assert sayfa.oku({"kind": "network", "url_pattern": "/api/metin"})["matched"] == 1
    assert sayfa.oku({"kind": "network", "request_id": 99999})["request"] is None

    # Yakalanmayan hata konsol tamponuna "error" olarak düşer.
    hatalar = sayfa.oku({"kind": "console", "only_errors": True})
    assert any("gecikmeli hata" in m["text"] for m in hatalar["messages"])


def test_izleyici_olmayan_sayfada_okuyucu_present_false_der(tarayici):
    page = tarayici.new_page()
    page.goto("data:text/html,<title>bos</title>")
    okuyucu = _read_monitor_source()
    durum = _monitor_state_source()

    assert page.evaluate(f"(a) => ({okuyucu})(a)", {"kind": "console"}) == {"present": False}
    assert page.evaluate(f"() => ({durum})()")["present"] is False
    page.close()


def test_temizle_bayragi_konsol_tamponunu_bosaltir_ve_izleyici_ikinci_kez_kurulmaz(sayfa):
    # İzleyici yeniden enjekte edilirse (izin sonrası `files` ile) sarmalama katlanmaz.
    sayfa.add_script_tag(path=str(EXTENSION / "pageMonitor.js"))
    sayfa.evaluate("console.log('tek')")
    assert sum(1 for m in sayfa.oku({"kind": "console"})["messages"] if m["text"] == "tek") == 1

    sayfa.oku({"kind": "console", "clear": True})
    assert sayfa.oku({"kind": "console"})["total"] == 0
    assert sayfa.durum()["present"] is True and sayfa.durum()["ready"] == "complete"
