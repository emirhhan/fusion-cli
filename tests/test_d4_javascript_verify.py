"""JavaScript kapısı: UTF-8 olmayan dosya, ESM hata mesajı, ölü süreç (A2-26, A2-28, A2-29)."""

from __future__ import annotations

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.javascript_verify import (
    JavaScriptSyntaxVerifier,
    NodeJavaScriptSyntaxChecker,
    SyntaxCheckResult,
)


class _Sahte:
    def __init__(self, sonuclar):
        self.sonuclar = sonuclar

    async def check(self, source, *, is_module):
        return self.sonuclar[is_module]


async def test_utf8_olmayan_dosya_dogrulayiciyi_dusurmez(tmp_path):
    yol = tmp_path / "eski.js"
    yol.write_bytes(b"var a = '\xe7\xfd\xfe';\n")  # cp1254 baytları, UTF-8 değil
    baglam = ToolContext(root=tmp_path)
    baglam.touched.add(yol)

    sonuc = await JavaScriptSyntaxVerifier(
        baglam, _Sahte({False: SyntaxCheckResult(ok=True)})
    ).verify()

    assert sonuc.ok


async def test_bilinmeyen_kipte_esm_dosyasinin_gercek_hatasi_gosterilir(tmp_path):
    yol = tmp_path / "app.js"
    yol.write_text("import x from './y.js';\nlet a = ;\n", encoding="utf-8")
    baglam = ToolContext(root=tmp_path)
    baglam.touched.add(yol)
    sahte = _Sahte(
        {
            False: SyntaxCheckResult(
                ok=False, detail="Cannot use import statement outside a module"
            ),
            True: SyntaxCheckResult(ok=False, detail="SyntaxError: Unexpected token ';'"),
        }
    )

    sonuc = await JavaScriptSyntaxVerifier(baglam, sahte).verify()

    assert not sonuc.ok
    assert "Unexpected token ';'" in sonuc.findings[0]
    assert "Cannot use import" not in sonuc.findings[0]


async def test_zaman_asiminda_cikmis_surec_oldurulurken_istisna_sizmaz(monkeypatch):
    import asyncio

    class _Surec:
        returncode = None

        async def communicate(self, veri):
            await asyncio.sleep(10)

        def kill(self):
            raise ProcessLookupError

        async def wait(self):
            return 0

    async def _baslat(*args, **kwargs):
        return _Surec()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _baslat)

    sonuc = await NodeJavaScriptSyntaxChecker("node", timeout_s=0.01).check("1", is_module=False)

    assert sonuc.ok
