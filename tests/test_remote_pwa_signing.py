"""PWA imza kodu (JS) ile sunucu imzası (Python) birebir aynı sonucu vermeli."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from fusion_cli.remote.signing import sign

PWA = Path(__file__).resolve().parents[1] / "src/fusion_cli/remote/pwa"
NODE = shutil.which("node") or "/opt/homebrew/opt/node@22/bin/node"

SCRIPT = """
import {{ importKey, sign }} from "{module}";
const key = await importKey("{secret}");
const body = new TextEncoder().encode('{{"method":"service.status","params":{{}}}}');
console.log(await sign(key, "POST", "/v1/rpc", 1700000000, "nonce-1", 7, body));
"""


@pytest.mark.skipif(not Path(NODE).exists() and shutil.which("node") is None, reason="node yok")
def test_js_ve_python_imzalari_ayni(tmp_path: Path) -> None:
    secret = bytes(range(32))
    script = tmp_path / "t.mjs"
    script.write_text(SCRIPT.format(module=(PWA / "signing.js").as_uri(), secret=secret.hex()))
    result = subprocess.run([NODE, str(script)], capture_output=True, text=True, check=True)
    body = json.dumps({"method": "service.status", "params": {}}, separators=(",", ":")).encode()
    expected = sign(secret, "POST", "/v1/rpc", 1700000000, "nonce-1", 7, body)
    assert result.stdout.strip() == expected


def test_pwa_dosyalari_var_ve_ic_html_enjeksiyonu_yok() -> None:
    for name in (
        "index.html",
        "app.js",
        "api.js",
        "approvals.js",
        "chat.js",
        "dom.js",
        "screen-stream.js",
        "store.js",
        "signing.js",
        "sw.js",
        "manifest.webmanifest",
        "styles.css",
        "icon-192.png",
        "icon-512.png",
        "apple-touch-icon.png",
    ):
        assert (PWA / name).is_file()
    for script in PWA.glob("*.js"):
        assert "innerHTML" not in script.read_text()
    manifest = json.loads((PWA / "manifest.webmanifest").read_text())
    assert manifest["display"] == "standalone"
    sizes = {icon["sizes"] for icon in manifest["icons"]}
    assert {"192x192", "512x512"} <= sizes  # ana ekran simgesi PNG olmalı (iOS SVG'yi yok sayar)
    assert any(icon["purpose"] == "maskable" for icon in manifest["icons"])
    shell = (PWA / "sw.js").read_text()
    assert "/v1/" in shell  # RPC önbelleğe alınmaz


def test_pwa_mobil_uygulama_duzeni_alt_sekme_ve_guvenli_alan() -> None:
    html = (PWA / "index.html").read_text()
    css = (PWA / "styles.css").read_text()
    script = (PWA / "app.js").read_text()
    assert "viewport-fit=cover" in html and 'rel="apple-touch-icon"' in html
    assert 'id="sekmeler"' in html and "safe-area-inset-bottom" in css
    for tab in ("sohbetler", "gorevler", "onaylar", "ekran", "ayarlar"):
        assert f'id: "{tab}"' in script
    assert "-apple-system" in css and "font: 14px" in css  # Kits yazı tipi ve 14 px taban
    assert "style=" not in html  # CSP style-src 'self': satır içi stil yok


def test_pwa_ekran_bolumu_guvenli_ve_kapsama_bagli() -> None:
    script = (PWA / "app.js").read_text()
    html = (PWA / "index.html").read_text()
    assert 'scope: "desktop.observe"' in script  # kapsam yoksa sekme hiç açılmaz
    assert "scopes.includes(tab.scope)" in script
    assert 'data-view="ekran"' in html
    assert "data:image/jpeg;base64," in (PWA / "screen-view.js").read_text()


def test_pwa_ekran_kutusu_en_boy_oranini_korur() -> None:
    css = (PWA / "styles.css").read_text()
    assert "object-fit: contain" in css
    assert "width: auto" in css and "max-height: 100%" in css  # kare kutuya sığar, esnemez


def test_pwa_her_modul_sunuluyor_ve_onbellege_aliniyor() -> None:
    import re

    from fusion_cli.remote.asgi import _STATIC

    served = {path.lstrip("/") for path in _STATIC}
    shell = (PWA / "sw.js").read_text()
    for script in PWA.glob("*.js"):
        assert script.name in served, f"{script.name} ASGI'de sunulmuyor"
        for target in re.findall(r'from "\./([a-z-]+\.js)"', script.read_text()):
            assert target in served and (PWA / target).is_file(), f"{script.name} → {target}"
        if script.name != "sw.js":
            assert f'"/{script.name}"' in shell, f"{script.name} sw önbelleğinde yok"
    for name, _type in _STATIC.values():
        assert (PWA / name).is_file()


def test_pwa_mobil_kullanim_ozellikleri_baglanmis() -> None:
    chat = (PWA / "chat.js").read_text()
    app = (PWA / "app.js").read_text()
    for needle in (
        "chats.history",
        "uploads.put",
        "tasks.cancel",
        "tasks.create",
        "renderRichText",
    ):
        assert needle in chat, needle
    for needle in (
        "projects.create",
        "schedules.run",
        "schedules.enable",
        "models.select",
        "kits.run",
    ):
        assert needle in app, needle
    assert "SpeechRecognition" in (PWA / "voice.js").read_text()
    assert "media.get" in (PWA / "media.js").read_text()


@pytest.mark.skipif(not Path(NODE).exists() and shutil.which("node") is None, reason="node yok")
def test_sohbet_satirlari_proje_suzgeci_ve_canli_gorev_birlesimi(tmp_path: Path) -> None:
    script = tmp_path / "t.mjs"
    script.write_text(
        f"""
import {{ chatRows, filterRows }} from "{(PWA / "views-chats.js").as_uri()}";
const ctx = {{
  chats: [
    {{ id: "c1", title: "Eski", updatedAt: 10, projectId: "p1", root: "/k" }},
    {{ id: "c2", title: "Yeni", updatedAt: 30, projectId: null, root: "/k" }},
  ],
  chatProjects: {{ c3: "p1" }},
  tasks: [
    {{ runId: "r1", chatId: "c1", state: "running", createdAt: 50, summary: "calisiyor" }},
    {{ runId: "r2", chatId: "c3", state: "queued", createdAt: 40, summary: "henuz diskte yok" }},
    {{ runId: "r3", chatId: "", state: "done", createdAt: 5, summary: "eski gorev" }},
  ],
}};
const rows = chatRows(ctx);
console.log(JSON.stringify({{
  order: rows.map((r) => r.title),
  activeOnC1: rows.find((r) => r.chatId === "c1").task.runId,
  p1: filterRows(rows, "p1").map((r) => r.chatId),
  none: filterRows(rows, "none").map((r) => r.chatId),
}}));
"""
    )
    done = subprocess.run([NODE, str(script)], capture_output=True, text=True, check=True)
    result = json.loads(done.stdout)
    assert result["order"] == ["henuz diskte yok", "Yeni", "Eski", "eski gorev"]
    assert result["activeOnC1"] == "r1"
    assert result["p1"] == ["c3", "c1"] and result["none"] == ["c2", ""]
