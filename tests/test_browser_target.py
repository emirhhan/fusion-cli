"""Hedef çözücü gerçek Chromium'da: belirsizlik, seçim kutusu, jQuery yazımı."""

from __future__ import annotations

import pytest

from fusion_cli.tools.browser_target import (
    TargetError,
    fill_or_select,
    normalize_selector,
    resolve,
)

_FORM = """<!doctype html><html><body><form>
<label>Ad <input name="ad"></label>
<label>E-posta <input name="eposta" type="email"></label>
<select name="konu"><option value="satis">Satış</option><option>Destek</option></select>
<textarea name="mesaj"></textarea>
<input type="hidden" name="gizli" value="x">
<button type="submit">Gönder</button> <a href="/ana">Ana sayfa</a>
</form></body></html>"""


def test_jquery_contains_yazimi_cevrilir():
    assert normalize_selector('a:contains("Ana sayfa")') == 'a:has-text("Ana sayfa")'
    assert normalize_selector("li:contains('Sepet') > a") == 'li:has-text("Sepet") > a'
    assert normalize_selector("button:contains(Gönder)") == 'button:has-text("Gönder")'
    assert normalize_selector("input[name=ad]") == "input[name=ad]"


async def test_gercek_formda_belirsizlik_secim_ve_ustune_yazma(tmp_path):
    playwright = pytest.importorskip("playwright.async_api")
    sayfa_dosyasi = tmp_path / "form.html"
    sayfa_dosyasi.write_text(_FORM, encoding="utf-8")
    try:
        async with playwright.async_playwright() as p:
            tarayici = await p.chromium.launch()
            page = await tarayici.new_page()
            await page.goto(sayfa_dosyasi.as_uri())

            with pytest.raises(TargetError) as belirsiz:
                await resolve(page, "input", 2000)
            ad = await resolve(page, 'input[name="ad"]', 2000)
            ilk = await fill_or_select(ad, "Deneme Kullanıcı")
            ikinci = await fill_or_select(ad, "Destek")
            konu = await resolve(page, "select", 2000)
            secim = await fill_or_select(konu, "destek")
            dugme = await resolve(page, 'button:contains("Gönder")', 2000)
            secilen = await page.eval_on_selector("select", "e => e.value")
            await tarayici.close()
    except playwright.Error as hata:
        pytest.skip(f"tarayıcı yok: {hata}")

    mesaj = str(belirsiz.value)
    assert "2 görünür öğeye uyuyor" in mesaj
    assert 'input[name="ad"]' in mesaj and 'input[name="eposta"]' in mesaj
    assert ilk == 'input[name="ad"] alanına yazıldı'
    assert "önceki değer 'Deneme Kullanıcı' silindi" in ikinci
    assert secim == "select[name=\"konu\"] → 'Destek' seçildi" and secilen == "Destek"
    assert dugme.tag == "button"
