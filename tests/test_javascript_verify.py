"""JavaScript sözdizimi kapısının davranış testleri."""

from __future__ import annotations

import shutil

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import verification
from fusion_cli.engines.agent.verification import build_verifier

from .fakes import make_config

node_required = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="JavaScript sözdizimi denetimi için Node.js gerekli",
)


async def _verify(tmp_path, name: str, content: str):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    context = ToolContext(root=tmp_path)
    context.touched.add(path)
    verifier = build_verifier(
        make_config(
            runtime={
                "browser_verification": False,
                "visual_verification": False,
            }
        ),
        root=tmp_path,
        tool_context=context,
    )

    assert verifier is not None
    return await verifier.verify()


@node_required
async def test_inline_javascript_sondan_eksikse_turu_dusurur(tmp_path):
    """Debug nesnesinin metinde bulunması, parse olmayan betiği geçerli kılmaz."""
    html = """<main><canvas></canvas></main>
    <script>
    window.__FUSION_GAME_DEBUG__ = {};
    for (const enemy of enemies) {
        enemy.move();
    </script>"""

    result = await _verify(tmp_path, "index.html", html)

    assert result.ok is False
    assert any("index.html" in finding for finding in result.findings)
    assert any("Unexpected end of input" in finding for finding in result.findings)


@node_required
async def test_gecerli_inline_javascript_bulgu_uretmez(tmp_path):
    html = """<main><canvas></canvas></main>
    <script>
    window.__FUSION_GAME_DEBUG__ = {};
    for (const enemy of enemies) {
        enemy.move();
    }
    </script>"""

    result = await _verify(tmp_path, "index.html", html)

    assert result.ok is True, result.findings


@node_required
async def test_json_script_javascript_gibi_ayristirilmaz(tmp_path):
    html = """<main>veri</main>
    <script type="application/json">{"eksik": [}</script>"""

    result = await _verify(tmp_path, "index.html", html)

    assert result.ok is True, result.findings


@node_required
async def test_module_script_module_sozdizimiyle_dogrulanir(tmp_path):
    html = """<main>uygulama</main>
    <script type="module">export const started = true;</script>"""

    result = await _verify(tmp_path, "index.html", html)

    assert result.ok is True, result.findings


@node_required
async def test_dokunulan_javascript_dosyasi_parse_edilmiyorsa_turu_dusurur(tmp_path):
    result = await _verify(tmp_path, "game.js", "const state = {;")

    assert result.ok is False
    assert any("game.js" in finding for finding in result.findings)
    assert any("Unexpected token" in finding for finding in result.findings)


@node_required
@pytest.mark.parametrize("name", ["game.mjs", "game.cjs"])
async def test_javascript_module_uzantilari_da_sozdizimi_kapisina_girer(tmp_path, name):
    result = await _verify(tmp_path, name, "const state = {;")

    assert result.ok is False
    assert any(name in finding for finding in result.findings)


@node_required
async def test_module_paketindeki_javascript_module_olarak_dogrulanir(tmp_path):
    (tmp_path / "package.json").write_text('{"type": "module"}', encoding="utf-8")

    result = await _verify(tmp_path, "game.js", "export const started = true;")

    assert result.ok is True, result.findings


@node_required
async def test_baglami_belirsiz_javascript_gecerli_module_olabilir(tmp_path):
    result = await _verify(tmp_path, "game.js", "export const started = true;")

    assert result.ok is True, result.findings


@node_required
async def test_commonjs_uzantisi_module_sozdizimini_kabul_etmez(tmp_path):
    result = await _verify(tmp_path, "game.cjs", "export const started = true;")

    assert result.ok is False
    assert any("Unexpected token" in finding for finding in result.findings)


async def test_node_yoksa_opsiyonel_kapi_turu_dusurmez(tmp_path, monkeypatch):
    monkeypatch.setattr(verification, "find_node_executable", lambda: None)

    result = await _verify(tmp_path, "game.js", "const state = {;")

    assert result.ok is True, result.findings
