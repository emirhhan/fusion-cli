"""Gateway panelinde dış değerler HTML/inline JS'e kaçışlanarak basılır (WP16).

Ölçüldü (29 Ekim): `p.name`, `p.id`, uzak katalog `m.id`/`m.provider` olduğu gibi
innerHTML'e ve `onclick="delKey('${p.id}')"` dizesine basılıyordu; `"` ya da `'`
içeren bir kimlik öznitelik/JS dizesini kırıyordu.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

PANEL = Path(__file__).resolve().parents[1] / "src/fusion_cli/gateway/static/panel.js"
KOTU = "x\"'><img src=x onerror=alert(1)>"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node gerekli")

_SARMAL = """
const vm = require('vm'), fs = require('fs');
const document = {
  getElementById: () => ({}),
  querySelectorAll: () => [],
  addEventListener: () => {},
};
const ctx = { document, window: {} };
vm.createContext(ctx);
const kaynak = fs.readFileSync(process.argv[1], 'utf8');
vm.runInContext(kaynak + '\\n;globalThis.__out = (() => { ' + process.argv[2] + ' })();', ctx);
console.log(JSON.stringify(ctx.__out));
"""


def _calistir(govde: str) -> object:
    sonuc = subprocess.run(
        ["node", "-e", _SARMAL, str(PANEL), govde],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return json.loads(sonuc.stdout)


def test_saglayici_karti_kotu_kimlik_ve_adi_kacislar() -> None:
    kotu = json.dumps(KOTU)
    kart = _calistir(
        f"return providerCard({{name: {kotu}, id: {kotu}, implemented: true,"
        " kind: 'api_key', status: 's', configured: true, keys: 1});"
    )
    assert isinstance(kart, str)
    assert "<img" not in kart
    assert "&lt;img" in kart
    # İnline işleyiciler JSON dizesi + HTML kaçışı olarak gider; tırnak öznitelikten çıkamaz.
    assert "delKey(&quot;" in kart
    assert "togglePcard(&quot;" in kart
    assert "'" not in kart.split("onclick=")[1].split(">")[0]


def test_esc_ve_jsarg_ozellikleri() -> None:
    assert _calistir("return esc('<a href=\"x\">&\\'')") == "&lt;a href=&quot;x&quot;&gt;&amp;&#39;"
    assert _calistir('return jsArg("a\'b")') == "&quot;a&#39;b&quot;"
