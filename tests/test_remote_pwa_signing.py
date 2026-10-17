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
        "signing.js",
        "sw.js",
        "manifest.webmanifest",
        "styles.css",
    ):
        assert (PWA / name).is_file()
    assert "innerHTML" not in (PWA / "app.js").read_text()
    manifest = json.loads((PWA / "manifest.webmanifest").read_text())
    assert manifest["display"] == "standalone"
    shell = (PWA / "sw.js").read_text()
    assert "/v1/" in shell  # RPC önbelleğe alınmaz


def test_pwa_ekran_bolumu_guvenli_ve_kapsama_bagli() -> None:
    script = (PWA / "app.js").read_text()
    html = (PWA / "index.html").read_text()
    assert 'includes("desktop.observe")' in script  # kapsam yoksa bölüm hiç açılmaz
    assert 'id="ekran"' in html and "hidden" in html.split('id="ekran"')[1][:60]
    assert "innerHTML" not in script
    assert "data:image/jpeg;base64," in script  # CSP img-src data: ile uyumlu
