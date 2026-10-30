"""Service worker ağ ve önbellek yokluğunda da geçerli HTTP yanıtı verir."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

WORKER = Path(__file__).resolve().parents[1] / "src/fusion_cli/remote/pwa/sw.js"
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node yok")
def test_worker_sorgulu_sayfa_ve_bos_onbellekte_gecerli_yanit_verir() -> None:
    script = r"""
const vm = require('node:vm');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const handlers = {};
let cached;
let matched;
const match = async (request, options) => {matched = {request, options}; return cached;};
const context = {
 URL, Response,
 self: {addEventListener: (name, fn) => handlers[name] = fn},
 fetch: async () => {throw new Error('offline');},
 caches: {match, open: async () => ({match})},
};
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), context);
async function run(mode, path) {
 let promise;
 handlers.fetch({request:{method:'GET',url:'https://fusion.test'+path,mode},
   respondWith: response => promise = response});
 return await promise;
}
(async () => {
 cached = new Response('kabuk');
 assert.equal(await (await run('navigate','/?yenile=20261017')).text(), 'kabuk');
 assert.equal(matched.options?.ignoreSearch, true, 'Sayfa sorgusu önbellek eşleşmesini bozmamalı');
 cached = undefined;
 const response = await run('navigate','/?yenile=20261017');
 assert.ok(response instanceof Response, 'Boş önbellek null yanıt döndüremez');
 assert.equal(response.status, 503);
 assert.match(await response.text(), /Tailscale/);
 const asset = await run('cors','/app.js');
 assert.ok(asset instanceof Response);
 assert.equal(asset.status, 503);
 assert.notEqual(matched.options?.ignoreSearch, true, 'Modül sürüm sorgusu korunmalı');
 assert.equal(await run('cors','/v1/rpc'), undefined, 'RPC yakalanmamalı');
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    subprocess.run([str(NODE), "-e", script, str(WORKER)], check=True, timeout=15)


@pytest.mark.skipif(NODE is None, reason="node yok")
def test_worker_kurulumu_tek_dosya_404_verse_de_dusmez() -> None:
    """R1-34. Ölçüldü (30 Ekim): `cache.addAll` tek 404'te bütün kurulumu reddediyordu."""
    script = r"""
const vm = require('node:vm');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const handlers = {};
const added = [];
const cache = {add: async (url) => {
 if (url === '/chat.js') throw new Error('404');
 added.push(url);
}};
const context = {
 URL, Response, Promise,
 self: {addEventListener: (name, fn) => handlers[name] = fn, skipWaiting() {}},
 caches: {open: async () => cache},
};
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), context);
let pending;
handlers.install({waitUntil: (promise) => pending = promise});
pending.then(() => {
 assert.ok(added.includes('/app.js'), 'diğer dosyalar önbelleğe alınmalı');
 assert.ok(!added.includes('/chat.js'));
}).catch(error => {console.error(error); process.exitCode = 1;});
"""
    subprocess.run([str(NODE), "-e", script, str(WORKER)], check=True, timeout=15)


def test_sohbet_metni_yalniz_gonderim_basarisindan_sonra_temizlenir() -> None:
    """R1-21: `tasks.create` başarısızsa kutudaki metin ve ekler korunur."""
    chat = (WORKER.parent / "chat.js").read_text()
    submit = chat[chat.index("async function submit()") : chat.index("async function stop()")]
    assert submit.index("tasks.create") < submit.index('input.value = ""')
    assert "catch (error)" in submit
