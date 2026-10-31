"""Önizleme paneli tamamlanması (P-041): launch.json sunucuları, konsol/ağ günlüğü, RPC, /onizleme.

Ölçüldü (31 Ekim): önizleme yalnız dosyalardan anlaşılan türleri başlatabiliyordu; adlı
yapılandırma, konsol/ağ okuma, panelden başlatma ve ekran görüntüsü RPC'si yoktu.
"""

from __future__ import annotations

import asyncio
import http.server
import json
import os
import sys
import threading
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.cli.repl.commands import build_registry, parse
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config import trust
from fusion_cli.core.events import PreviewReady
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import preview_log_tools, tool_profiles
from fusion_cli.engines.agent.preview_tools import run_preview
from fusion_cli.engines.agent.site_verify import running_preview
from fusion_cli.memory.factory import null_memory
from fusion_cli.tools import preview_launch, preview_log, preview_server
from fusion_cli.tools.preview_launch import (
    LaunchConfig,
    LaunchConfigError,
    LaunchUntrustedError,
    is_local_url,
    join_local_page,
    launch_env,
    load_launch_configs,
)
from fusion_cli.tools.preview_log import ConsoleEntry, NetworkEntry, PageLog
from fusion_cli.tools.preview_server import PreviewError, PreviewKind, RunningPreview

from .fakes import make_config


@pytest.fixture(autouse=True)
def _sunuculari_kapat(tmp_path, monkeypatch):
    # Güven kaydı gerçek kullanıcı dizinine DEĞİL geçici dosyaya yazılır.
    monkeypatch.setattr(trust, "trust_store_file", lambda: tmp_path / "guven-kaydi.json")
    yield
    preview_launch.stop_all_launches()
    preview_server.stop_all()


def _guvenli(name, executable, args, port, url=None, **kw) -> LaunchConfig:
    """Testlerin elle kurduğu komutlu yapılandırma: dosya karması yerine açık güven."""
    return LaunchConfig(name, executable, tuple(args), port, url, trusted=True, **kw)


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
    assert web == LaunchConfig(
        "web", "npm", ("run", "dev"), 5173, None, source=".fusion/launch.json"
    )
    assert web.command_text == "npm run dev" and web.address == "http://127.0.0.1:5173/"
    assert loaded.warnings == () and not loaded.trusted and web.needs_trust and not api.needs_trust
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
def test_gecersiz_yapilandirma_atlanir_ve_uyari_olur_digerleri_calisir(tmp_path, config, parca):
    # Ölçüldü (31 Ekim): tek geçersiz kayıt dosyanın tamamını kullanılamaz yapıyordu.
    _yaz(tmp_path, [config, {"name": "saglam", "url": "http://localhost:9"}])
    loaded = load_launch_configs(tmp_path)
    assert [c.name for c in loaded.configs] == ["saglam"]
    assert len(loaded.warnings) == 1 and parca.replace("\\", "") in loaded.warnings[0]
    assert "atlandı" in loaded.warnings[0]
    with pytest.raises(LaunchConfigError, match="Mevcut: saglam"):
        preview_launch.find_launch_config(tmp_path, "x")


def test_bozuk_json_hata_tekrarli_ad_ve_bilinmeyen_alan_uyari(tmp_path):
    (tmp_path / ".fusion").mkdir()
    (tmp_path / ".fusion" / "launch.json").write_text("{bozuk", encoding="utf-8")
    with pytest.raises(LaunchConfigError, match="geçerli JSON değil"):
        load_launch_configs(tmp_path)

    _yaz(
        tmp_path,
        [
            {"name": "a", "url": "http://localhost:1", "autoPort": True},
            {"name": "a", "url": "http://localhost:2"},
        ],
    )
    loaded = load_launch_configs(tmp_path)
    assert [c.url for c in loaded.configs] == ["http://localhost:1"]
    assert any("autoPort" in w and "yok sayıldı" in w for w in loaded.warnings)
    assert any("tekrar" in w for w in loaded.warnings)


def test_bozuk_fusion_dosyasinda_claude_dosyasina_dusulur(tmp_path):
    (tmp_path / ".fusion").mkdir()
    (tmp_path / ".fusion" / "launch.json").write_text("[", encoding="utf-8")
    _yaz(tmp_path, [{"name": "Web Server", "url": "http://localhost:3000"}], ".claude/launch.json")
    loaded = load_launch_configs(tmp_path)
    # Adda iç boşluk serbesttir (kabuğa gitmez); bozuk Fusion dosyası uyarı olur.
    assert loaded.source == ".claude/launch.json" and loaded.configs[0].name == "Web Server"
    assert loaded.warnings and ".fusion/launch.json" in loaded.warnings[0]


def test_env_alani_okunur_ve_gecersizse_kayit_atlanir(tmp_path):
    _yaz(
        tmp_path,
        [
            {"name": "web", "url": "http://localhost:1", "env": {"VITE_BASE": "/x", "A": "1"}},
            {"name": "kotu", "url": "http://localhost:2", "env": {"1x": "y"}},
        ],
    )
    loaded = load_launch_configs(tmp_path)
    assert [c.name for c in loaded.configs] == ["web"]
    assert loaded.configs[0].env == (("A", "1"), ("VITE_BASE", "/x"))
    assert loaded.warnings and "`env`" in loaded.warnings[0]


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
    config = _guvenli(
        "web", sys.executable, ("-m", "http.server", str(port), "--bind", "127.0.0.1"), port
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
    config = _guvenli(
        "kirik", sys.executable, ("-c", "import sys; print('PORT yok'); sys.exit(3)"), 65000
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


# --- Güven: komutlu yapılandırma ancak dosya güvenilirse çalışır --------------------- #


def _komutlu(tmp_path, dosya=".fusion/launch.json", port=None):
    port = port or preview_server.free_port()
    _yaz(
        tmp_path,
        [
            {
                "name": "web",
                "runtimeExecutable": sys.executable,
                "runtimeArgs": ["-m", "http.server", str(port), "--bind", "127.0.0.1"],
                "port": port,
            },
            {"name": "api", "url": f"http://127.0.0.1:{port}/"},
        ],
        dosya,
    )
    return port


@pytest.mark.parametrize("dosya", [".fusion/launch.json", ".claude/launch.json"])
async def test_guvenilmeyen_projede_komut_calismaz_fusion_trust_sonrasi_calisir(tmp_path, dosya):
    # Ölçüldü (31 Ekim): indirilmiş deponun launch.json komutu güven denetimi olmadan
    # (tam ortamla) başlıyordu; yalnız `url` ile bağlanma onay gerektirmez.
    _sayfa(tmp_path)
    _komutlu(tmp_path, dosya)
    config = preview_launch.find_launch_config(tmp_path, "web")
    assert config.needs_trust and config.source == dosya

    with pytest.raises(LaunchUntrustedError, match="fusion trust") as hata:
        await preview_launch.start_launch(tmp_path, config)
    assert "http.server" in str(hata.value) and dosya in str(hata.value)
    assert preview_launch.running_launch(tmp_path, "web") is None

    trust.trust_project(tmp_path)
    config = preview_launch.find_launch_config(tmp_path, "web")
    assert not config.needs_trust and load_launch_configs(tmp_path).trusted
    preview = await preview_launch.start_launch(tmp_path, config)
    assert preview.process is not None and preview_server.responds(preview.url)
    assert preview_launch.stop_launch(tmp_path, "web")

    # Dosya değişince güven kendiliğinden düşer.
    _komutlu(tmp_path, dosya)
    assert preview_launch.find_launch_config(tmp_path, "web").needs_trust


def test_launch_hint_guvenilmeyen_komutlari_onermez(tmp_path):
    from fusion_cli.engines.agent.preview_launch_run import launch_hint

    _komutlu(tmp_path)
    ipucu = launch_hint(tmp_path)
    assert "'api'" in ipucu and "name='…'" in ipucu
    assert "'web'" in ipucu and "fusion trust" in ipucu and "çağırma" in ipucu
    trust.trust_project(tmp_path)
    assert "fusion trust" not in launch_hint(tmp_path) and "'web', 'api'" in launch_hint(tmp_path)


def test_panelden_guven_dosyanin_su_anki_halini_onaylar(tmp_path):
    assert preview_launch.trust_launch_file(tmp_path) is None
    _komutlu(tmp_path)
    assert preview_launch.trust_launch_file(tmp_path) == ".fusion/launch.json"
    assert not preview_launch.find_launch_config(tmp_path, "web").needs_trust


def test_surec_ortaminda_sirlar_yok_port_ve_env_var():
    config = _guvenli("web", "npm", ("run", "dev"), 5173, env=(("VITE_X", "1"),))
    base = {
        "PATH": "/usr/bin",
        "HOME": "/Users/ali",
        "OPENAI_API_KEY": "sk-gizli",
        "ANTHROPIC_API_KEY": "gizli",
        "FUSION_SECRET_KEY": "gizli",
        "DB_PASSWORD": "gizli",
        "GITHUB_TOKEN": "gizli",
        "NODE_OPTIONS": "--max-old-space-size=4096",
    }
    env = launch_env(config, base)
    assert env["PORT"] == "5173" and env["VITE_X"] == "1" and env["HOME"] == "/Users/ali"
    assert env["NODE_OPTIONS"] == "--max-old-space-size=4096" and "/usr/bin" in env["PATH"]
    for gizli in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "FUSION_SECRET_KEY",
        "DB_PASSWORD",
        "GITHUB_TOKEN",
    ):
        assert gizli not in env  # fmt: skip


async def test_eszamanli_baslatma_tek_surec_acar(tmp_path):
    # Ölçüldü (31 Ekim): kontrol ile kayıt arası await'te ikinci çağrı birincinin kaydını
    # eziyor, ezilen süreç sahipsiz kalıyordu (Durdur ve atexit onu kapatmazdı).
    _sayfa(tmp_path)
    port = preview_server.free_port()
    config = _guvenli(
        "web", sys.executable, ("-m", "http.server", str(port), "--bind", "127.0.0.1"), port
    )
    birinci, ikinci = await asyncio.gather(
        preview_launch.start_launch(tmp_path, config),
        preview_launch.start_launch(tmp_path, config),
    )
    assert birinci is ikinci and birinci.process is not None
    assert preview_launch.running_launches(tmp_path) == (("web", birinci),)


async def test_cwd_sembolik_bagla_kok_disina_cikamaz(tmp_path):
    kok = tmp_path / "proje"
    kok.mkdir()
    (tmp_path / "dis").mkdir()
    (kok / "link").symlink_to(tmp_path / "dis", target_is_directory=True)
    config = _guvenli("web", sys.executable, ("-c", "pass"), 65001, cwd="link")
    with pytest.raises(PreviewError, match="kökü dışına"):
        await preview_launch.start_launch(kok, config)


def test_page_yalniz_yol_olabilir():
    base = "http://127.0.0.1:5173/"
    assert join_local_page(base, "/shop/") == "http://127.0.0.1:5173/shop/"
    assert join_local_page(base, None) == base and join_local_page(base, "  ") == base
    for kotu in ("http://169.254.169.254/latest/", "//evil.example/x", "https://127.0.0.1:5173/"):
        with pytest.raises(PreviewError, match="yalnız yol"):
            join_local_page(base, kotu)


def test_varsayilan_adres_en_son_baslatilan_ve_alt_klasor_dahil(tmp_path):
    kok = tmp_path.resolve()
    adli = RunningPreview(kok, PreviewKind.LAUNCH, "http://127.0.0.1:1/", attached=True)
    tespit = RunningPreview(kok, PreviewKind.STATIC, "http://127.0.0.1:2/", attached=True)
    preview_launch._RUNNING[(kok, "api")] = adli
    preview_server._RUNNING[kok] = tespit
    assert preview_launch.default_preview_url(tmp_path) == "http://127.0.0.1:2/"
    adli.started_at = tespit.started_at + 1
    assert preview_launch.default_preview_url(tmp_path) == "http://127.0.0.1:1/"
    # Alt klasör köküyle başlatılan sunucu da üst kökten görünür.
    preview_server._RUNNING.clear()
    preview_launch._RUNNING.clear()
    alt = RunningPreview(kok / "sub", PreviewKind.LAUNCH, "http://127.0.0.1:3/", attached=True)
    preview_launch._RUNNING[(kok / "sub", "x")] = alt
    assert preview_launch.default_preview_url(tmp_path) == "http://127.0.0.1:3/"
    assert running_preview(tmp_path / "sub") is alt and running_preview(tmp_path) is None


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
        # Kapanış kapısı adlı sunucuyu da görür (ikinci geçici sunucu açmaz).
        calisan = running_preview(tmp_path)
        assert calisan is not None and calisan.last_probe["url"] == f"http://127.0.0.1:{port}/"

        dis = await run_preview(
            SimpleNamespace(publisher=yayinci),
            {"name": "site", "page": "http://169.254.169.254/latest/"},
            ToolContext(root=tmp_path),
        )  # type: ignore[arg-type]
        assert not dis.ok and "yalnız yol" in dis.output
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
    konsol, ag, goruntu = preview_log_tools.preview_log_tools(SimpleNamespace())
    assert (konsol.name, ag.name) == ("preview_console", "preview_network")
    assert goruntu.name == "preview_screenshot"
    assert not konsol.mutating and not ag.mutating and not goruntu.mutating

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
    konsol, ag, _ = preview_log_tools.preview_log_tools(SimpleNamespace())

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
            "cwd": "", "baglan": False, "calisiyor": False, "guven_gerekli": True,
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


def test_onizleme_durdur_komutu_ve_uyarilar(tmp_path):
    state = ReplState(
        config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )
    kok = tmp_path.resolve()
    preview_launch._RUNNING[(kok, "api")] = RunningPreview(
        kok, PreviewKind.LAUNCH, "http://127.0.0.1:1/", attached=True
    )
    assert _komut(state, "/onizleme durdur api") == "'api' önizlemesi durduruldu."
    assert _komut(state, "/onizleme durdur api") == "'api' adlı çalışan önizleme yok."
    assert _komut(state, "/onizleme stop").startswith("''")

    _yaz(
        tmp_path,
        [
            {
                "name": "web",
                "runtimeExecutable": "npm",
                "runtimeArgs": ["run", "dev"],
                "port": 5173,
            },
            {"name": "x"},
        ],
    )
    liste = _komut(state, "/onizleme")
    assert "fusion trust" in liste and "! .fusion/launch.json [x]" in liste


# --- Günlük: yerel olmayan yönlendirme, Chromium eksik, sembolik bağ ------------------ #


def test_izlenen_istek_yalniz_yerel_ya_da_sayfa_ici():
    assert preview_log.allowed_request_url("http://localhost:5173/app.js")
    assert preview_log.allowed_request_url("data:text/plain,x")
    assert preview_log.allowed_request_url("blob:http://localhost:5173/abc")
    assert not preview_log.allowed_request_url("http://192.168.1.1/")
    assert not preview_log.allowed_request_url("https://cdn.example.com/x.js")
    assert not preview_log.allowed_request_url("http://169.254.169.254/latest/meta-data/")


def test_sembolik_bag_ekran_goruntusu_hedefi_yazilmaz(tmp_path):
    kurban = tmp_path / "kurban.txt"
    kurban.write_text("dokunma", encoding="utf-8")
    kok = tmp_path / "proje"
    (kok / ".fusion").mkdir(parents=True)
    (kok / ".fusion" / "onizleme-ekran.png").symlink_to(kurban)
    assert preview_log.save_screenshot(kok, b"PNG") == ""
    assert kurban.read_text(encoding="utf-8") == "dokunma"

    # Klasörün kendisi bağ ise de yazılmaz.
    kok2 = tmp_path / "proje2"
    kok2.mkdir()
    (tmp_path / "dis").mkdir()
    (kok2 / ".fusion").symlink_to(tmp_path / "dis", target_is_directory=True)
    assert preview_log.save_screenshot(kok2, b"PNG") == ""
    assert not (tmp_path / "dis" / "onizleme-ekran.png").exists()


async def test_chromium_indirilmemisse_turkce_yonlendirme(monkeypatch):
    # Ölçüldü (31 Ekim): yalnız ImportError yolunda Türkçe mesaj vardı; "Executable doesn't
    # exist" İngilizce ve yönlendirmesiz gösteriliyordu. Sahte playwright modülüyle sınanır.
    class _SahteHataError(Exception):
        pass

    class _Chromium:
        async def launch(self):
            raise _SahteHataError(
                "BrowserType.launch: Executable doesn't exist at /x/chrome\n"
                "Please run the following command to download new browsers: playwright install"
            )

    class _Driver:
        chromium = _Chromium()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    sahte = types.ModuleType("playwright.async_api")
    sahte.Error = _SahteHataError  # type: ignore[attr-defined]
    sahte.async_playwright = lambda: _Driver()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright.async_api", sahte)

    log = await preview_log.collect_page_log("http://localhost:5173/")
    assert log.error == preview_log.CHROMIUM_MISSING


def _playwright_hazir() -> bool:
    try:
        import playwright.async_api  # noqa: F401
    except ImportError:
        return False
    cache = Path(
        os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or Path.home() / "Library/Caches/ms-playwright"
    )
    return any(cache.glob("chromium*")) if cache.is_dir() else False


class _GunlukSayfasi(http.server.BaseHTTPRequestHandler):
    """Konsol yazan, eksik kaynak isteyen ve dışa yönlendiren küçük site."""

    def log_message(self, *args: object) -> None:
        del args

    def do_GET(self) -> None:
        if self.path == "/dis":
            self.send_response(302)
            self.send_header("Location", "http://192.0.2.1/")
            self.end_headers()
            return
        if self.path == "/yok.css":
            self.send_response(404)
            self.end_headers()
            return
        body = (
            "<!doctype html><title>G</title><link rel=stylesheet href=/yok.css>"
            "<script>console.log('hazır');console.error('x tanımsız');"
            "fetch('/api').catch(()=>0);</script><p>metin</p>"
        ).encode()
        self.send_response(200 if self.path != "/api" else 500)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.mark.skipif(not _playwright_hazir(), reason="Playwright/Chromium kurulu değil")
async def test_gercek_tarayici_konsol_ag_toplar_ve_dis_yonlendirmeyi_engeller():
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _GunlukSayfasi)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        taban = f"http://127.0.0.1:{httpd.server_address[1]}"
        log = await preview_log.collect_page_log(
            f"{taban}/", preview_log.CaptureOptions(settle_ms=300, screenshot=True)
        )
        assert not log.error, log.error
        seviyeler = {(e.level, e.text) for e in log.console}
        assert ("log", "hazır") in seviyeler and ("error", "x tanımsız") in seviyeler
        durumlar = {e.url.rsplit("/", 1)[-1]: e.status for e in log.requests}
        assert durumlar[""] == 200 and durumlar["yok.css"] == 404 and durumlar["api"] == 500
        assert log.screenshot is not None and log.screenshot[:4] == b"\x89PNG"

        dis = await preview_log.collect_page_log(f"{taban}/dis")
        assert "yönlendirdi" in dis.error and "192.0.2.1" in dis.error
    finally:
        httpd.shutdown()
        httpd.server_close()


# --- Ajan aracı: preview_screenshot ------------------------------------------------- #


async def test_preview_screenshot_araci_goruntu_dondurur_ve_dosyaya_yazar(tmp_path, monkeypatch):
    secenekler: list[preview_log.CaptureOptions] = []

    async def sahte(url, options=preview_log.DEFAULT_CAPTURE):
        secenekler.append(options)
        return PageLog(url, console=(ConsoleEntry("error", "x"),), screenshot=b"\x89PNG-ajan")

    monkeypatch.setattr(preview_log_tools, "collect_page_log", sahte)
    arac = next(
        t for t in preview_log_tools.preview_log_tools(None) if t.name == "preview_screenshot"
    )  # type: ignore[arg-type]
    assert not arac.mutating

    sonuc = await arac.run(
        {"url": "http://localhost:5173/", "width": 375, "height": 812, "color_scheme": "dark"},
        ToolContext(root=tmp_path),
    )
    assert sonuc.ok and "375×812" in sonuc.output and "dark tema" in sonuc.output
    assert "Dosya: .fusion/onizleme-ekran.png" in sonuc.output and "1 hata" in sonuc.output
    assert (tmp_path / ".fusion" / "onizleme-ekran.png").read_bytes() == b"\x89PNG-ajan"
    assert sonuc.content and sonuc.content[0].mime_type == "image/png"
    assert secenekler[0].screenshot and secenekler[0].color_scheme == "dark"

    yok = await arac.run({}, ToolContext(root=tmp_path))
    assert not yok.ok and "start_preview" in yok.output


async def test_rpc_guven_gerekli_ve_guven_sonrasi_baslar(tmp_path):
    _sayfa(tmp_path)
    port = _komutlu(tmp_path)
    lines: list[str] = []
    session = AppSession(lines.append, root=tmp_path, home=tmp_path.parent / ".fusion-home")
    try:
        liste = await _rpc(session, lines, "onizleme.yapilandirmalar", {})
        red = await _rpc(session, lines, "onizleme.baslat", {"ad": "web"})
        guven = await _rpc(session, lines, "onizleme.guven", {})
        liste2 = await _rpc(session, lines, "onizleme.yapilandirmalar", {})
        baslat = await _rpc(session, lines, "onizleme.baslat", {"ad": "web"})
        durdur = await _rpc(session, lines, "onizleme.durdur", {"ad": "web"})
    finally:
        await session.close()

    assert liste["guvenli"] is False and liste["uyarilar"] == []
    assert liste["yapilandirmalar"][0]["guven_gerekli"] is True
    assert liste["yapilandirmalar"][1]["guven_gerekli"] is False
    assert red["ok"] is False and red["guven_gerekli"] is True and "http.server" in red["komut"]
    assert guven == {"ok": True, "dosya": ".fusion/launch.json"}
    assert liste2["guvenli"] is True and liste2["yapilandirmalar"][0]["guven_gerekli"] is False
    assert baslat["ok"] is True and baslat["url"] == f"http://127.0.0.1:{port}/"
    assert durdur["durduruldu"] is True
