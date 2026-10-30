"""Gateway panel betiklerini Node `vm` içinde sahte DOM ile çalıştıran test yardımcısı."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / "src/fusion_cli/gateway/static"
NODE_YOK = shutil.which("node") is None
node_gerekli = pytest.mark.skipif(NODE_YOK, reason="node gerekli")

_SARMAL = """
const vm = require('vm'), fs = require('fs');
const els = {};
const el = (id) => (els[id] ||= {
  id, value: '', textContent: '', innerHTML: '', className: '', checked: false, disabled: false,
  dataset: {}, style: {}, attrs: {},
  classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
  setAttribute(k, v) { this.attrs[k] = v; }, removeAttribute() {},
  querySelector() { return el('_q'); }, querySelectorAll() { return []; },
});
const document = {
  getElementById: el, querySelector: () => el('_q'), querySelectorAll: () => [],
  addEventListener() {}, createElement: () => el('_c'),
};
const ctx = { document, window: {}, console, location: { origin: 'http://x' }, setTimeout, clearTimeout,
  setInterval: () => 0, navigator: {}, URL, Promise, JSON };
vm.createContext(ctx);
for (const f of JSON.parse(process.argv[1])) vm.runInContext(fs.readFileSync(f, 'utf8'), ctx);
ctx.els = els;
const sonuc = vm.runInContext('(async () => { ' + process.argv[2] + ' })()', ctx);
sonuc.then((v) => console.log(JSON.stringify(v ?? null)),
  (e) => { console.error(String(e && e.stack || e)); process.exit(2); });
"""


def calistir(govde: str, dosyalar: tuple[str, ...] = ("panel.js", "web-sessions.js")) -> object:
    """`govde` bir async işlev gövdesidir; `return` ettiği değer JSON olarak döner."""
    yollar = [str(STATIC / ad) for ad in dosyalar]
    sonuc = subprocess.run(
        ["node", "-e", _SARMAL, json.dumps(yollar), govde],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert sonuc.returncode == 0, sonuc.stderr
    return json.loads(sonuc.stdout)
