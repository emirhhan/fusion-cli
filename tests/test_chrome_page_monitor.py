"""Eklentinin sayfa izleyicisi (`pageMonitor.js`) ve okuyucusu (`readMonitor`) GERÇEK Chromium'da.

Konsol iletileri, hata olayları, `fetch`/XHR istekleri ve yanıt gövdesi `debugger` izni
olmadan sayfa içinde toplanır (P-042). Playwright Chromium'u kurulu değilse atlanır.
"""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
    match = re.search(r"export function monitorState\([^)]*\)\s*\{.*?\n\}\n", core, re.S)
    assert match, "monitorState core.js içinde bulunamadı"
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
    yield _okuyuculu(page)
    page.close()


def _okuyuculu(page):
    """Sayfaya eklentinin okuyucularını (`readMonitor`, `monitorState`) bağla."""
    okuyucu = _read_monitor_source()
    durum = _monitor_state_source()
    page.oku = lambda args: page.evaluate(f"(a) => ({okuyucu})(a)", args)
    page.durum = lambda task_origin=None: page.evaluate(
        f"(origin) => ({durum})(origin)", task_origin
    )
    return page


@pytest.fixture(scope="module")
def akis_sunucu():
    """Gerçek akış sunucusu (`page.route` akışı taklit edemez): `/` boş sayfa, `/akis`
    başlıkları gönderir, bir parça yazar ve kapanmayı BEKLER; `/buyuk` 200 KB düz metin.
    Sayfa aynı kaynaktan açılır: Chromium açık bir siteden 127.0.0.1'e fetch'i engeller."""
    bitir = threading.Event()

    class _Isleyici(BaseHTTPRequestHandler):
        def do_GET(self):  # http.server sözleşmesi
            if self.path == "/akis":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(b"data: ilk\n\n")
                self.wfile.flush()
                bitir.wait(15)
                return
            if self.path == "/buyuk":
                govde = (("x" * 1000 + "\n") * 200).encode()
                tur = "text/plain; charset=utf-8"
            else:
                govde = b"<!doctype html><title>Ak\xc4\xb1\xc5\x9f</title><body>akis</body>"
                tur = "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", tur)
            self.send_header("Content-Length", str(len(govde)))
            self.end_headers()
            self.wfile.write(govde)

        def log_message(self, *_args):
            return

    sunucu = ThreadingHTTPServer(("127.0.0.1", 0), _Isleyici)
    sunucu.daemon_threads = True
    threading.Thread(target=sunucu.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{sunucu.server_port}"
    bitir.set()
    sunucu.shutdown()


@pytest.fixture
def akis_sayfa(tarayici, akis_sunucu):
    page = tarayici.new_page()
    page.add_init_script(path=str(EXTENSION / "pageMonitor.js"))
    page.goto(f"{akis_sunucu}/")
    yield _okuyuculu(page)
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
    # The adapter must execute the real optional-origin reader, including its guard.
    assert sayfa.oku({"kind": "console", "__taskOrigin": "http://izle.test"}) == hepsi
    assert sayfa.durum("http://izle.test")["present"] is True
    with pytest.raises(playwright_sync.Error, match="başlangıçtaki sitesi değişti"):
        sayfa.durum("http://foreign.test")
    with pytest.raises(playwright_sync.Error, match="başlangıçtaki sitesi değişti"):
        sayfa.oku({"kind": "console", "clear": True, "__taskOrigin": "http://foreign.test"})
    assert sayfa.oku({"kind": "console"}) == hepsi, "foreign-origin guard cannot clear the buffer"


def test_fetch_ve_xhr_istekleri_durum_tur_sure_ve_govdeyle_kaydedilir(sayfa):
    sayfa.click("#go")
    sayfa.wait_for_function("window.__sonuc && window.__sonuc.adet === 3")
    sayfa.wait_for_function("globalThis.__fusionMonitor.pending === 0")
    # Gövde başlıklardan SONRA ayrı okunur; bekleyen sayısı başlıkta düşer.
    sayfa.wait_for_function(
        "globalThis.__fusionMonitor.network.filter(r => typeof r.body === 'string').length === 3"
    )
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


def test_akis_yaniti_bekleyen_sayisini_baslikta_dusurur_ve_govde_biriktirmez(akis_sayfa):
    # Ölçüldü (31 Ekim, bağımsız inceleme): `clone().text()` SSE akışı bitene dek tüm gövdeyi
    # bellekte biriktiriyor, `pending` o süre boyunca düşmüyor ve `wait network_idle` hiç
    # boşa düşmüyordu.
    akis_sayfa.evaluate("fetch('/akis').then(r => { window.__akis = r.status; })")
    akis_sayfa.wait_for_function("window.__akis === 200")
    akis_sayfa.wait_for_timeout(300)

    ag = akis_sayfa.oku({"kind": "network", "url_pattern": "/akis"})
    istek = ag["requests"][0]

    assert akis_sayfa.durum()["pending"] == 0, "akış sürerken bekleyen istek sayılmamalı"
    assert istek["status"] == 200 and istek["type"] == "text/event-stream"
    assert istek["has_body"] is False, "event-stream gövdesi saklanmaz"


def test_buyuk_metin_govdesi_16_kb_ta_kesilir_sayfanin_kendi_okumasi_bozulmaz(akis_sayfa):
    uzunluk = akis_sayfa.evaluate("fetch('/buyuk').then(r => r.text()).then(t => t.length)")
    akis_sayfa.wait_for_function(
        "globalThis.__fusionMonitor.network.some("
        "r => r.url.includes('/buyuk') && typeof r.body === 'string')"
    )

    kimlik = akis_sayfa.oku({"kind": "network", "url_pattern": "/buyuk"})["requests"][0]["id"]
    kayit = akis_sayfa.oku({"kind": "network", "request_id": kimlik})["request"]

    assert uzunluk == 200 * 1001, "sayfanın kendi fetch'i tam gövdeyi almalı"
    assert len(kayit["body"]) == 16384 and kayit["truncated"] is True
    assert akis_sayfa.durum()["pending"] == 0
