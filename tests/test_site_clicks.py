"""Tıklamayla değişen sekmeler ve kaydırıcı okları kopyada yerel betikle çalışır.

Ölçüldü (sneaksup): "Kadın / Erkek / Çocuk" sekmeleri düz span'lardı, React ürünleri
değiştiriyordu; kopyada sekmeler ve şerit okları ölüydü.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

_SAYFA = """<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;font:16px sans-serif} .sekmeler span{cursor:pointer;padding:4px 8px}
.sekmeler span.aktif{font-weight:700} .kirp{overflow:hidden;width:400px}
.serit{display:flex;gap:0} .kart{flex:0 0 100px;height:60px}
.ok{cursor:pointer;width:20px;height:20px;display:inline-block}
</style></head><body><main><section id="bolum">
<div class="sekmeler"><span class="aktif">Kadın</span><span>Erkek</span></div>
<div class="ok ok-prev" aria-label="Önceki"></div>
<div class="ok ok-next" aria-label="Sonraki"></div>
<div class="kirp"><div class="serit" id="serit"></div></div></section></main>
<script>
const urunler={Kadın:['k1','k2','k3','k4','k5','k6','k7','k8'],
  Erkek:['e1','e2','e3','e4','e5','e6']};
const ciz=(ad)=>{document.getElementById('serit').innerHTML=urunler[ad]
  .map((u)=>`<div class="kart"><p>${u}</p></div>`).join('');
  document.querySelectorAll('.sekmeler span')
    .forEach((s)=>s.classList.toggle('aktif',s.textContent===ad));};
document.querySelectorAll('.sekmeler span').forEach((s)=>s.onclick=()=>ciz(s.textContent));
ciz('Kadın');
</script></body></html>"""


async def _durumlar(tmp_path: Path) -> dict[str, object]:
    from playwright.async_api import async_playwright

    from fusion_cli.tools.site_capture import CAPTURE_SCRIPT
    from fusion_cli.tools.site_clicks import (
        CLICK_STATE_CSS,
        INTERACTIONS_RUNTIME,
        capture_click_states,
    )

    kaynak = tmp_path / "kaynak.html"
    kaynak.write_text(_SAYFA, encoding="utf-8")
    async with async_playwright() as p:
        tarayici = await p.chromium.launch()
        sayfa = await tarayici.new_page(viewport={"width": 800, "height": 600})
        await sayfa.goto(kaynak.as_uri())
        gruplar = await capture_click_states(sayfa)
        veri = await sayfa.evaluate(CAPTURE_SCRIPT.read_text(encoding="utf-8"))
        kopya = tmp_path / "kopya.html"
        kopya.write_text(
            f"<!doctype html><html><head><meta charset='utf-8'><style>{veri['css']}\n"
            f"{CLICK_STATE_CSS}</style></head><body>{veri['main']}<script>"
            f"{INTERACTIONS_RUNTIME.read_text(encoding='utf-8')}</script></body></html>",
            encoding="utf-8",
        )
        await sayfa.goto(kopya.as_uri())
        gorunen = (
            "() => [...document.querySelectorAll('.kart p')].filter((p) => {"
            "const r = p.getBoundingClientRect(); return r.width > 0 && r.left >= 0"
            " && r.right <= 400;}).map((p) => p.textContent).join(',')"
        )
        durum: dict[str, object] = {"gruplar": gruplar, "ilk": await sayfa.evaluate(gorunen)}
        await sayfa.locator("[data-kopya-acik] .sekmeler span", has_text="Erkek").click()
        durum["erkek"] = await sayfa.evaluate(gorunen)
        await sayfa.locator("[data-kopya-acik] .sekmeler span", has_text="Kadın").click()
        await sayfa.locator("[data-kopya-acik] .ok-next").click()
        await sayfa.wait_for_timeout(500)
        durum["ileri"] = await sayfa.evaluate(gorunen)
        await sayfa.locator("[data-kopya-acik] .ok-prev").click()
        await sayfa.wait_for_timeout(500)
        durum["geri"] = await sayfa.evaluate(gorunen)
        await tarayici.close()
    return durum


def test_sekme_halleri_ve_kaydirici_oklari_kopyada_calisir(tmp_path):
    playwright = pytest.importorskip("playwright.async_api")
    try:
        durum = asyncio.run(_durumlar(tmp_path))
    except playwright.Error as hata:
        pytest.skip(f"tarayıcı yok: {hata}")

    assert durum["gruplar"] == ("Kadın / Erkek",)
    assert durum["ilk"] == "k1,k2,k3,k4"
    assert durum["erkek"] == "e1,e2,e3,e4"
    assert durum["ileri"] == "k5,k6,k7,k8"
    assert durum["geri"] == "k1,k2,k3,k4"
