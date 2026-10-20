"""Yerel HTML bağımlılıklarının gerçek dosya varlığıyla denetlenmesi."""

from __future__ import annotations

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.verification import WebVerifier


async def _verify(tmp_path, html, name="index.html"):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"<html><head>{html}</head><body><main>x</main></body></html>")
    context = ToolContext(root=tmp_path)
    context.touched.add(path)
    return await WebVerifier(context).verify()


async def test_eksik_script_ve_stylesheet_engelleyici(tmp_path):
    result = await _verify(
        tmp_path, '<link rel="stylesheet" href="styles.css"><script src="script.js"></script>'
    )
    assert not result.ok
    assert any("styles.css" in finding for finding in result.findings)
    assert any("script.js" in finding for finding in result.findings)


async def test_dokunulmamis_mevcut_bagimliliklar_gecer(tmp_path):
    (tmp_path / "style.css").write_text("main { color: red; }")
    (tmp_path / "app.js").write_text("console.log('x')")
    result = await _verify(
        tmp_path, '<link rel="stylesheet" href="style.css"><script src="app.js"></script>'
    )
    assert result.ok


async def test_alt_dizin_query_fragment_ve_kodlanmis_yol(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app file.js").write_text("void 0")
    result = await _verify(
        tmp_path, '<script src="../assets/app%20file.js?v=1#x"></script>', "pages/index.html"
    )
    assert result.ok


async def test_ayni_basename_yanlis_dizinde_basari_uretmez(tmp_path):
    (tmp_path / "app.js").write_text("void 0")
    result = await _verify(tmp_path, '<script src="app.js"></script>', "pages/index.html")
    assert not result.ok
    assert any("app.js" in finding for finding in result.findings)


async def test_dis_kaynaklar_ve_stylesheet_olmayan_linkler_atlanir(tmp_path):
    result = await _verify(
        tmp_path,
        '<script src="https://example.com/app.js"></script>'
        '<script src="//example.com/app.js"></script>'
        '<script src="data:text/javascript,void%200"></script>'
        '<script src="blob:https://example.com/a"></script>'
        '<link rel="preconnect" href="https://example.com">'
        '<link rel="icon" href="missing.ico">',
    )
    assert result.ok


async def test_base_ve_kok_goreli_yollar(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("void 0")
    result = await _verify(
        tmp_path,
        '<base href="/assets/"><script src="app.js"></script>'
        '<script src="/assets/app.js"></script>',
        "pages/index.html",
    )
    assert result.ok


async def test_dis_base_yerel_olmayan_hedefi_atlar(tmp_path):
    result = await _verify(
        tmp_path, '<base href="https://example.com/"><script src="app.js"></script>'
    )
    assert result.ok


async def test_eksikler_olusturulunca_ayni_kapi_gecer(tmp_path):
    markup = '<script src="app.js"></script>'
    failed = await _verify(tmp_path, markup)
    assert not failed.ok
    (tmp_path / "app.js").write_text("void 0")
    passed = await _verify(tmp_path, markup)
    assert passed.ok


async def test_base_hedefindeki_eksik_dosya_engellenir(tmp_path):
    result = await _verify(
        tmp_path, '<base href="/assets/"><script src="missing.js"></script>', "pages/index.html"
    )
    assert not result.ok
    assert any("missing.js" in finding for finding in result.findings)


async def test_tek_tirnak_buyuk_harf_ve_coklu_rel_degeri(tmp_path):
    result = await _verify(tmp_path, "<LINK REL='alternate stylesheet' HREF='style.css'>")
    assert not result.ok
    assert any("style.css" in finding for finding in result.findings)


async def test_kodlanmis_ust_dizin_url_kokunu_asamaz(tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    (tmp_path / "outside.js").write_text("void 0")
    result = await _verify(root, '<script src="%2e%2e/outside.js"></script>')
    assert not result.ok
    assert any("outside.js" in finding for finding in result.findings)
    (root / "outside.js").write_text("void 0")
    assert (await _verify(root, '<script src="%2e%2e/outside.js"></script>')).ok


async def test_file_semasi_mevcut_olsa_da_dogrulanmadan_gecmez(tmp_path):
    local = tmp_path / "app.js"
    local.write_text("void 0")
    result = await _verify(tmp_path, f'<script src="{local.as_uri()}"></script>')
    assert not result.ok
    assert any("file" in finding and "doğrulanamadı" in finding for finding in result.findings)


async def test_kodlanmis_ayirici_sessizce_dosya_yoluna_cevrilmez(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("void 0")
    result = await _verify(tmp_path, '<script src="assets%2fapp.js"></script>')
    assert not result.ok
    assert any("ayırıcı" in finding for finding in result.findings)


async def test_kodlanmis_ve_duz_ust_dizin_sirasi_url_ile_ayni(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "app.js").write_text("void 0")
    markup = '<script src="a/%2e%2e/../app.js"></script>'
    assert not (await _verify(tmp_path, markup)).ok
    (tmp_path / "app.js").write_text("void 0")
    assert (await _verify(tmp_path, markup)).ok


async def test_base_kodlanmis_ve_duz_ust_dizin_sirasi(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "app.js").write_text("void 0")
    markup = '<base href="a/%2e%2e/../"><script src="app.js"></script>'
    assert not (await _verify(tmp_path, markup)).ok
    (tmp_path / "app.js").write_text("void 0")
    assert (await _verify(tmp_path, markup)).ok
