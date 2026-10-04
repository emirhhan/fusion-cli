"""Tarayıcı kabul alanının yerel fikstür sitesi ve istek kaydı.

Sunucu 127.0.0.1'de boş bir portta ayrı thread'de çalışır; her isteği
`<workdir>/.kabul_fikstur_kaydi.json` dosyasına ekler. Denetçi sunucu nesnesine değil
bu dosyaya bakar (hazırlık ve denetim farklı çağrılardır).
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

#: Fikstür HTML dosyalarının klasörü (uzun metin koda gömülmez).
SITE_DIR = Path(__file__).resolve().parent / "browser_site"
#: İstek kaydının çalışma klasöründeki dosya adı.
RECORD_FILENAME = ".kabul_fikstur_kaydi.json"
HOST = "127.0.0.1"
#: Bir POST gövdesinin kabul edilen en büyük boyutu (bayt).
MAX_BODY_BYTES = 65536
#: Yol -> HTML dosyası. `/tablo` sayfa parametresine göre ayrıca çözülür.
_STATIC_PAGES = {
    "/": "index.html",
    "/form": "form.html",
    "/sekme": "sekme.html",
    "/tehlike": "tehlike.html",
}
_TABLE_PAGES = {"1": "tablo_1.html", "2": "tablo_2.html"}
SUBMIT_PATH = "/gonder"


@dataclass(frozen=True, slots=True)
class RequestRecord:
    """Sunucunun gördüğü tek istek."""

    method: str
    path: str
    query: str
    body: str
    #: İsteği yapan istemci. Eski kayıtlarda yoktur (boş kalır).
    user_agent: str = ""


def read_records(workdir: Path) -> tuple[RequestRecord, ...] | None:
    """Kayıt dosyasını oku; dosya yok ya da bozuksa None (denetçi geçersiz sayar)."""
    path = workdir / RECORD_FILENAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, list):
        return None
    try:
        return tuple(RequestRecord(**item) for item in raw)
    except TypeError:
        return None


class _Recorder:
    """İstekleri kilit altında JSON dosyasına ekler."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._records: list[RequestRecord] = []
        self._flush()

    def add(self, record: RequestRecord) -> None:
        with self._lock:
            self._records.append(record)
            self._flush()

    def _flush(self) -> None:
        payload = [asdict(record) for record in self._records]
        self._path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _page_for(path: str, query: str) -> str | None:
    """Yola karşılık gelen HTML dosyasının adı; bilinmeyen yol için None."""
    if path == "/tablo":
        page = parse_qs(query).get("sayfa", ["1"])[0]
        return _TABLE_PAGES.get(page)
    return _STATIC_PAGES.get(path)


def _make_handler(recorder: _Recorder) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            """Konsola yazma; kayıt zaten JSON dosyasında."""

        def _reply(self, status: int, page: str | None) -> None:
            body = b"" if page is None else (SITE_DIR / page).read_bytes()
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _record(self, body: str) -> tuple[str, str]:
            parts = urlsplit(self.path)
            agent = self.headers.get("User-Agent") or ""
            recorder.add(RequestRecord(self.command, parts.path, parts.query, body, agent))
            return parts.path, parts.query

        def do_GET(self) -> None:
            path, query = self._record("")
            page = _page_for(path, query)
            self._reply(200 if page else 404, page)

        def do_POST(self) -> None:
            length = min(int(self.headers.get("Content-Length") or 0), MAX_BODY_BYTES)
            body = self.rfile.read(length).decode("utf-8", errors="replace")
            path, _ = self._record(body)
            ok = path == SUBMIT_PATH
            self._reply(200 if ok else 404, "tesekkur.html" if ok else None)

    return Handler


@contextmanager
def serve(workdir: Path) -> Iterator[str]:
    """Fikstür sitesini başlat; temel adresi ver, çıkışta sunucuyu kapat."""
    recorder = _Recorder(workdir / RECORD_FILENAME)
    server = ThreadingHTTPServer((HOST, 0), _make_handler(recorder))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://{HOST}:{server.server_address[1]}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
