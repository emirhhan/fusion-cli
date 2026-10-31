"""Önizleme paneli tamamlanması (P-041): launch.json sunucuları, konsol/ağ günlüğü, RPC, /onizleme.

Ölçüldü (31 Ekim): önizleme yalnız dosyalardan anlaşılan türleri başlatabiliyordu; adlı
yapılandırma, konsol/ağ okuma, panelden başlatma ve ekran görüntüsü RPC'si yoktu.
"""

from __future__ import annotations

import http.server
import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.cli.repl.commands import build_registry, parse
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.core.events import PreviewReady
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import preview_log_tools, tool_profiles
from fusion_cli.engines.agent.preview_tools import run_preview
from fusion_cli.memory.factory import null_memory
from fusion_cli.tools import preview_launch, preview_log, preview_server
from fusion_cli.tools.preview_launch import (
    LaunchConfig,
    LaunchConfigError,
    is_local_url,
    load_launch_configs,
)
from fusion_cli.tools.preview_log import ConsoleEntry, NetworkEntry, PageLog
from fusion_cli.tools.preview_server import PreviewError

from .fakes import make_config


@pytest.fixture(autouse=True)
def _sunuculari_kapat():
    yield
    preview_launch.stop_all_launches()
    preview_server.stop_all()


class _Yayinci:
    def __init__(self) -> None:
        self.olaylar: list[object] = []

    def publish(self, olay: object) -> None:
        self.olaylar.append(olay)


def _yaz(root: Path, configs: list[dict[str, object]], dosya: str = ".fusion/launch.json") -> Path:
    path = root / dosya
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": "0.0.1", "configurations": configs}), encoding="utf-8")
    return path


def _sayfa(root: Path) -> None:
    (root / "index.html").write_text(
        "<!doctype html><title>Launch</title><main><h1>Merhaba</h1>"
        "<p>Bu sayfa launch.json yapılandırmasıyla sunuluyor, yeterince uzun metin.</p></main>",
        encoding="utf-8",
    )


# --- launch.json okuma ------------------------------------------------------------- #


def test_dosya_yoksa_bos_liste(tmp_path):
    loaded = load_launch_configs(tmp_path)
    assert loaded.configs == () and loaded.source is None


def test_fusion_dosyasi_okunur_ve_alanlar_eslenir(tmp_path):
    _yaz(
        tmp_path,
        [
            {
                "name": "web",
                "runtimeExecutable": "npm",
                "runtimeArgs": ["run", "dev"],
                "port": 5173,
            },
            {"name": "api", "url": "http://localhost:8000/health", "cwd": "backend"},
        ],
    )

    loaded = load_launch_configs(tmp_path)

    assert loaded.source == ".fusion/launch.json"
    web, api = loaded.configs
    assert web == LaunchConfig("web", "npm", ("run", "dev"), 5173, None)
    assert web.command_text == "npm run dev" and web.address == "http://127.0.0.1:5173/"
    assert api.is_attach and api.address == "http://localhost:8000/health" and api.cwd == "backend"


def test_claude_code_dosyasi_uyumluluk_icin_okunur_fusion_dosyasi_oncelikli(tmp_path):
    _yaz(tmp_path, [{"name": "claude", "url": "http://localhost:3000"}], ".claude/launch.json")
    assert load_launch_configs(tmp_path).source == ".claude/launch.json"

    _yaz(tmp_path, [{"name": "fusion", "url": "http://localhost:3001"}])
    loaded = load_launch_configs(tmp_path)
    assert loaded.source == ".fusion/launch.json" and [c.name for c in loaded.configs] == ["fusion"]


@pytest.mark.parametrize(
    ("config", "parca"),
    [
        ({"name": "x", "url": "https://example.com"}, "yerel bir http adresi"),
        ({"name": "x"}, "`runtimeExecutable` ya da `url`"),
        ({"name": "x", "runtimeExecutable": "npm"}, "`port` ya da `url`"),
        ({"name": "x", "runtimeExecutable": "npm", "port": 70000}, "1-65535"),
        ({"name": "x", "runtimeExecutable": "npm", "port": True}, "1-65535"),
        ({"name": "kötü ad!", "url": "http://localhost:1"}, "`name`"),
        ({"name": "x", "url": "http://localhost:1", "cwd": "../dis"}, "`cwd`"),
        ({"name": "x", "url": "http://localhost:1", "runtimeArgs": "run dev"}, "`runtimeArgs`"),
    ],
)
def test_gecersiz_yapilandirma_acik_hatayla_reddedilir(tmp_path, config, parca):
    _yaz(tmp_path, [config])
    with pytest.raises(LaunchConfigError, match=parca):
        load_launch_configs(tmp_path)


def test_bozuk_json_ve_tekrarli_ad_reddedilir(tmp_path):
    (tmp_path / ".fusion").mkdir()
    (tmp_path / ".fusion" / "launch.json").write_text("{bozuk", encoding="utf-8")
    with pytest.raises(LaunchConfigError, match="geçerli JSON değil"):
        load_launch_configs(tmp_path)

    _yaz(
        tmp_path,
        [{"name": "a", "url": "http://localhost:1"}, {"name": "a", "url": "http://localhost:2"}],
    )
    with pytest.raises(LaunchConfigError, match="benzersiz"):
        load_launch_configs(tmp_path)


def test_yalniz_yerel_http_adresleri_yerel_sayilir():
    assert is_local_url("http://localhost:5173/x") and is_local_url("http://127.0.0.1:1")
    assert is_local_url("http://[::1]:8080/")
    assert not is_local_url("https://localhost:5173") and not is_local_url(
        "http://evil.localhost.example"
    )
    assert not is_local_url(None) and not is_local_url("javascript:alert(1)")


# --- Başlatma ---------------------------------------------------------------------- #


def _yerel_sunucu(root: Path):
    handler = type("H", (http.server.SimpleHTTPRequestHandler,), {"log_message": lambda *a: None})
    httpd = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), lambda *a, **k: handler(*a, directory=str(root), **k)
    )
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


async def test_yalniz_url_verilen_yapilandirma_calisan_sunucuya_baglanir(tmp_path):
    _sayfa(tmp_path)
    httpd = _yerel_sunucu(tmp_path)
    try:
        port = httpd.server_address[1]
        config = LaunchConfig("api", None, (), None, f"http://127.0.0.1:{port}/")

        preview = await preview_launch.start_launch(tmp_path, config)

        assert (
            preview.url == f"http://127.0.0.1:{port}/"
            and preview.kind is preview_server.PreviewKind.LAUNCH
        )
        assert preview.process is None and preview_launch.running_launch(tmp_path, "api") is preview
        assert preview_launch.default_preview_url(tmp_path) == preview.url
        assert preview_launch.stop_launch(tmp_path, "api") is True
        assert preview_launch.running_launch(tmp_path, "api") is None
        assert preview_launch.stop_launch(tmp_path, "api") is False
    finally:
        httpd.shutdown()
        httpd.server_close()


async def test_url_yanit_vermiyorsa_baglanma_acik_hatayla_duser(tmp_path):
    with pytest.raises(PreviewError, match="yanıt vermiyor"):
        await preview_launch.start_launch(
            tmp_path, LaunchConfig("api", None, (), None, "http://127.0.0.1:9/")
        )


async def test_komutlu_yapilandirma_kabuksuz_baslatilir_ve_kapatilir(tmp_path):
    _sayfa(tmp_path)
    port = preview_server.free_port()
    config = LaunchConfig(
        "web", sys.executable, ("-m", "http.server", str(port), "--bind", "127.0.0.1"), port, None
    )

    preview = await preview_launch.start_launch(tmp_path, config)

    assert preview.url == f"http://127.0.0.1:{port}/" and preview.process is not None
    assert preview_server.responds(preview.url)
    # Aynı ada ikinci çağrı yeni süreç açmaz.
    assert await preview_launch.start_launch(tmp_path, config) is preview
    assert preview_launch.running_launches(tmp_path) == (("web", preview),)
    assert preview_launch.stop_launch(tmp_path, "web") is True
    await preview.process.wait()
    assert preview.process.returncode is not None


async def test_hemen_olen_komutun_ciktisi_hataya_eklenir(tmp_path):
    config = LaunchConfig(
        "kirik", sys.executable, ("-c", "import sys; print('PORT yok'); sys.exit(3)"), 65000, None
    )
    with pytest.raises(PreviewError) as hata:
        await preview_launch.start_launch(tmp_path, config)
    assert "PORT yok" in str(hata.value) and "kirik" in str(hata.value)


async def test_var_olmayan_ad_mevcutlari_sayar(tmp_path):
    _yaz(tmp_path, [{"name": "web", "url": "http://localhost:1"}])
    with pytest.raises(LaunchConfigError, match="Mevcut: web"):
        preview_launch.find_launch_config(tmp_path, "api")
    with pytest.raises(LaunchConfigError, match=r"launch\.json yok"):
        preview_launch.find_launch_config(tmp_path / "bos", "api")


# --- Ajan aracı: start_preview name= ----------------------------------------------- #


async def test_start_preview_name_ile_launch_yapilandirmasini_acar_ve_adres_yayinlar(tmp_path):
    _sayfa(tmp_path)
    httpd = _yerel_sunucu(tmp_path)
    try:
        port = httpd.server_address[1]
        _yaz(tmp_path, [{"name": "site", "url": f"http://127.0.0.1:{port}/"}])
        yayinci = _Yayinci()

        sonuc = await run_preview(
            SimpleNamespace(publisher=yayinci), {"name": "site"}, ToolContext(root=tmp_path)
        )  # type: ignore[arg-type]

        assert sonuc.ok and "Önizleme çalışıyor" in sonuc.output and "'site'" in sonuc.output
        assert "preview_console" in sonuc.output
        hazir = [olay for olay in yayinci.olaylar if isinstance(olay, PreviewReady)]
        assert len(hazir) == 1 and hazir[0].kind == "launch" and hazir[0].title == "Launch"
    finally:
        httpd.shutdown()
        httpd.server_close()


async def test_start_preview_bilinmeyen_ad_hatayi_modele_soyler(tmp_path):
    _yaz(tmp_path, [{"name": "web", "url": "http://localhost:1"}])
    sonuc = await run_preview(
        SimpleNamespace(publisher=_Yayinci()), {"name": "yok"}, ToolContext(root=tmp_path)
    )  # type: ignore[arg-type]
    assert not sonuc.ok and "Mevcut: web" in sonuc.output


async def test_tur_anlasilmazsa_launch_adlari_ipucu_olarak_eklenir(tmp_path):
    _yaz(
        tmp_path,
        [
            {"name": "web", "url": "http://localhost:1"},
            {"name": "api", "url": "http://localhost:2"},
        ],
    )
    sonuc = await run_preview(SimpleNamespace(publisher=_Yayinci()), {}, ToolContext(root=tmp_path))  # type: ignore[arg-type]
    assert not sonuc.ok and "'web', 'api'" in sonuc.output and "name='…'" in sonuc.output


# --- Konsol / ağ günlüğü ----------------------------------------------------------- #


def _gunluk(url: str = "http://localhost:5173/") -> PageLog:
    return PageLog(
        url,
        console=(
            ConsoleEntry("log", "hazır"),
            ConsoleEntry("error", "x tanımsız", "main.js:12"),
            ConsoleEntry("pageerror", "TypeError: y"),
        ),
        requests=(
            NetworkEntry("GET", f"{url}", 200, "document"),
            NetworkEntry("GET", f"{url}app.css", 404, "stylesheet"),
            NetworkEntry("POST", f"{url}api", 0, "fetch", "net::ERR_CONNECTION_REFUSED"),
        ),
    )


def test_konsol_ve_ag_metni_hatalari_one_alir():
    gunluk = _gunluk()
    assert gunluk.error_count == 2 and len(gunluk.failed_requests) == 2

    konsol = preview_log.format_console(gunluk)
    assert (
        konsol.startswith("3 konsol mesajı (2 hata)")
        and "[error] x tanımsız (main.js:12)" in konsol
    )
    assert preview_log.format_console(gunluk, only_errors=True).count("\n") == 2

    ag = preview_log.format_network(gunluk).splitlines()
    assert ag[0] == "3 istek, 2 başarısız:"
    assert (
        ag[1].startswith("404 GET")
        and ag[2].startswith("YOK POST")
        and "ERR_CONNECTION_REFUSED" in ag[2]
    )
    assert ag[3].startswith("200 GET")
    assert preview_log.format_network(gunluk, only_failed=True).count("\n") == 2
    assert preview_log.format_console(PageLog("u", error="Playwright yok")) == "Playwright yok"


def test_bekleme_ve_gorunum_sinirlanir():
    assert preview_log.clamp_settle(None) == preview_log.DEFAULT_SETTLE_MS
    assert preview_log.clamp_settle(True) == preview_log.DEFAULT_SETTLE_MS
    assert preview_log.clamp_settle(99_999) == preview_log.MAX_SETTLE_MS
    assert preview_log.clamp_settle(-5) == 0
    assert preview_log.clamp_viewport(375, None) == (375, preview_log.SCREENSHOT_HEIGHT)
    assert preview_log.clamp_viewport(10, 99_999) == (
        preview_log.MIN_VIEWPORT,
        preview_log.MAX_VIEWPORT,
    )


async def test_yerel_olmayan_adresin_gunlugu_okunmaz():
    gunluk = await preview_log.collect_page_log("https://example.com")
    assert gunluk.error == preview_log.NOT_LOCAL and gunluk.console == ()


async def test_preview_console_araci_calisan_onizleme_yoksa_ne_yapilacagini_soyler(tmp_path):
    konsol, ag = preview_log_tools.preview_log_tools(SimpleNamespace())
    assert (konsol.name, ag.name) == ("preview_console", "preview_network")
    assert not konsol.mutating and not ag.mutating

    sonuc = await konsol.run({}, ToolContext(root=tmp_path))
    assert not sonuc.ok and "start_preview" in sonuc.output

    dis = await ag.run({"url": "https://example.com"}, ToolContext(root=tmp_path))
    assert not dis.ok and "browser_open" in dis.output


async def test_preview_console_ve_network_gunlugu_metne_cevirir(tmp_path, monkeypatch):
    goruldu: list[tuple[str, int]] = []

    async def sahte(url, options=preview_log.DEFAULT_CAPTURE):
        goruldu.append((url, options.settle_ms))
        return _gunluk(url)

    monkeypatch.setattr(preview_log_tools, "collect_page_log", sahte)
    konsol, ag = preview_log_tools.preview_log_tools(SimpleNamespace())

    sonuc = await konsol.run(
        {"url": "http://localhost:5173/", "wait_ms": 2500, "only_errors": True},
        ToolContext(root=tmp_path),
    )
    assert (
        sonuc.ok
        and sonuc.output.startswith("http://localhost:5173/\n")
        and "[log]" not in sonuc.output
    )
    assert goruldu == [("http://localhost:5173/", 2500)]

    sonuc = await ag.run(
        {"url": "http://localhost:5173/", "only_failed": True}, ToolContext(root=tmp_path)
    )
    assert sonuc.ok and "404 GET" in sonuc.output and "200 GET" not in sonuc.output


def test_gunluk_araclari_soru_profilinde_gizli_kod_profilinde_acik():
    gizli_soru = tool_profiles.hidden_tools([tool_profiles.PROFILE_QUESTION])
    assert {"preview_console", "preview_network"} <= gizli_soru
    assert not {"preview_console", "preview_network"} & tool_profiles.hidden_tools(
        [tool_profiles.PROFILE_CODE]
    )


# --- Appserver RPC ----------------------------------------------------------------- #


async def _rpc(session: AppSession, lines: list[str], name: str, data: dict[str, object]) -> dict:
    request_id = f"o-{len(lines)}"
    await session.handle(Request(id=request_id, name=name, data=data))
    for line in reversed(lines):
        payload = json.loads(line)
        if payload.get("tip") == "sonuc" and payload.get("id") == request_id:
            return payload["veri"]
    raise AssertionError("sonuç bulunamadı")


async def test_rpc_yapilandirmalari_listeler_ve_calisma_durumunu_soyler(tmp_path):
    _yaz(
        tmp_path,
        [{"name": "web", "runtimeExecutable": "npm", "runtimeArgs": ["run", "dev"], "port": 5173}],
    )
    lines: list[str] = []
    session = AppSession(lines.append, root=tmp_path, home=tmp_path.parent / ".fusion-home")
    try:
        sonuc = await _rpc(session, lines, "onizleme.yapilandirmalar", {})
    finally:
        await session.close()

    assert sonuc["ok"] is True and sonuc["kaynak"] == ".fusion/launch.json"
    assert sonuc["yapilandirmalar"] == [
        {
            "ad": "web", "komut": "npm run dev", "port": 5173, "url": "http://127.0.0.1:5173/",
            "cwd": "", "baglan": False, "calisiyor": False,
        }
    ]  # fmt: skip


async def test_rpc_bozuk_dosyayi_ve_yerel_olmayan_adresi_reddeder(tmp_path):
    (tmp_path / ".fusion").mkdir()
    (tmp_path / ".fusion" / "launch.json").write_text("[", encoding="utf-8")
    lines: list[str] = []
    session = AppSession(lines.append, root=tmp_path, home=tmp_path.parent / ".fusion-home")
    try:
        liste = await _rpc(session, lines, "onizleme.yapilandirmalar", {})
        baslat = await _rpc(session, lines, "onizleme.baslat", {})
        gunluk = await _rpc(session, lines, "onizleme.gunluk", {"url": "https://example.com"})
        goruntu = await _rpc(session, lines, "onizleme.ekran_goruntusu", {"url": "file:///etc"})
        durdur = await _rpc(session, lines, "onizleme.durdur", {"ad": "yok"})
    finally:
        await session.close()

    assert liste["ok"] is False and "JSON" in liste["metin"] and liste["yapilandirmalar"] == []
    assert baslat["ok"] is False and "ad" in baslat["metin"]
    assert gunluk["ok"] is False and "localhost" in gunluk["metin"]
    assert goruntu["ok"] is False
    assert durdur == {"ok": True, "ad": "yok", "durduruldu": False}


async def test_rpc_baslat_calisan_sunucuya_baglanir_ve_durdurur(tmp_path):
    _sayfa(tmp_path)
    httpd = _yerel_sunucu(tmp_path)
    lines: list[str] = []
    session = AppSession(lines.append, root=tmp_path, home=tmp_path.parent / ".fusion-home")
    try:
        port = httpd.server_address[1]
        _yaz(tmp_path, [{"name": "api", "url": f"http://127.0.0.1:{port}/"}])
        baslat = await _rpc(session, lines, "onizleme.baslat", {"ad": "api"})
        liste = await _rpc(session, lines, "onizleme.yapilandirmalar", {})
        durdur = await _rpc(session, lines, "onizleme.durdur", {"ad": "api"})
    finally:
        await session.close()
        httpd.shutdown()
        httpd.server_close()

    assert baslat == {"ok": True, "ad": "api", "url": f"http://127.0.0.1:{port}/", "komut": ""}
    assert liste["yapilandirmalar"][0]["calisiyor"] is True
    assert durdur["durduruldu"] is True


async def test_rpc_gunluk_ve_ekran_goruntusu_yuku(tmp_path, monkeypatch):
    from fusion_cli.appserver import preview_rpc

    secenekler: list[preview_log.CaptureOptions] = []

    async def sahte(url, options=preview_log.DEFAULT_CAPTURE):
        secenekler.append(options)
        return PageLog(
            url, *(_gunluk(url).console, _gunluk(url).requests), screenshot=b"\x89PNG-sahte"
        )

    monkeypatch.setattr(preview_rpc, "collect_page_log", sahte)
    lines: list[str] = []
    session = AppSession(lines.append, root=tmp_path, home=tmp_path.parent / ".fusion-home")
    try:
        gunluk = await _rpc(
            session, lines, "onizleme.gunluk", {"url": "http://localhost:5173/", "bekle_ms": 300}
        )
        goruntu = await _rpc(
            session, lines, "onizleme.ekran_goruntusu",
            {
                "url": "http://localhost:5173/", "genislik": 375, "yukseklik": 812,
                "tema": "dark", "tam_sayfa": True,
            },
        )  # fmt: skip
    finally:
        await session.close()

    assert gunluk["ok"] is True and gunluk["hata_sayisi"] == 2 and gunluk["basarisiz_istek"] == 2
    assert gunluk["konsol"][1] == {"seviye": "error", "metin": "x tanımsız", "kaynak": "main.js:12"}
    assert gunluk["ag"][1]["durum"] == 404 and gunluk["ag"][1]["basarisiz"] is True
    assert secenekler[0].settle_ms == 300 and secenekler[0].screenshot is False

    assert (
        goruntu["ok"] is True
        and goruntu["mime"] == "image/png"
        and goruntu["yol"] == ".fusion/onizleme-ekran.png"
    )
    assert (tmp_path / ".fusion" / "onizleme-ekran.png").read_bytes() == b"\x89PNG-sahte"
    assert (goruntu["genislik"], goruntu["yukseklik"]) == (375, 812)
    assert (
        secenekler[1].color_scheme == "dark"
        and secenekler[1].full_page
        and secenekler[1].screenshot
    )


# --- REPL /onizleme ---------------------------------------------------------------- #


def _komut(state: ReplState, satir: str) -> str:
    name, argument = parse(satir)
    command = build_registry().get(name)
    assert command is not None
    return command.handler(state, argument)


def test_onizleme_komutu_listeler_ve_adla_ajana_gorev_verir(tmp_path):
    state = ReplState(
        config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )

    assert ".fusion/launch.json" in _komut(state, "/onizleme") and "Tanımlı sunucu yok" in _komut(
        state, "/preview"
    )

    _yaz(
        tmp_path,
        [{"name": "web", "runtimeExecutable": "npm", "runtimeArgs": ["run", "dev"], "port": 5173}],
    )
    liste = _komut(state, "/onizleme")
    assert "· web — npm run dev → http://127.0.0.1:5173/ [kapalı]" in liste

    assert "Mevcut: web" in _komut(state, "/onizleme api") and state.pending_task == ""

    cikti = _komut(state, "/onizleme web")
    assert "ajana veriliyor" in cikti
    task, _ = state.take_pending()
    assert "start_preview" in task and "name='web'" in task
