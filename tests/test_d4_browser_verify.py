"""Tarayıcı kapısı: ölçülemeyen durum sessiz geçmez, bozuk satır gözlemi düşürmez (A1-09)."""

from __future__ import annotations

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import browser_verify
from fusion_cli.engines.agent.browser_verify import (
    NOT_MEASURED_PREFIX,
    BrowserVerifier,
    _as_triples,
)


def _baglam(tmp_path):
    sayfa = tmp_path / "a.html"
    sayfa.write_text("<main>x</main>", encoding="utf-8")
    baglam = ToolContext(root=tmp_path)
    baglam.touched.add(sayfa)
    return baglam


async def test_playwright_yoksa_olculemedi_uyarisi_verir_ama_turu_dusurmez(tmp_path, monkeypatch):
    monkeypatch.setattr(browser_verify, "_playwright_available", lambda: False)

    sonuc = await BrowserVerifier(_baglam(tmp_path)).verify()

    assert sonuc.ok and sonuc.findings == ()
    assert sonuc.warnings and sonuc.warnings[0].startswith(NOT_MEASURED_PREFIX)


async def test_sayfa_acilamazsa_zaman_asimi_olculemedi_olarak_bildirilir(tmp_path, monkeypatch):
    monkeypatch.setattr(browser_verify, "_playwright_available", lambda: True)

    async def _zaman_asimi(self, pages):
        raise TimeoutError("page.goto 15000ms")

    monkeypatch.setattr(BrowserVerifier, "_observe", _zaman_asimi)

    sonuc = await BrowserVerifier(_baglam(tmp_path)).verify()

    assert sonuc.ok
    assert sonuc.warnings and "TimeoutError" in sonuc.warnings[0]


def test_bozuk_satir_gozlemin_tamamini_dusurmez():
    ham = [["a", 1, 2], ["b", None, 3], ["c", float("nan"), 1], ["d", float("inf"), 1], ["e", 5, 6]]

    assert _as_triples(ham) == (("a", 1, 2), ("e", 5, 6))


async def test_erken_olen_dev_sureci_45_sn_beklenmez():
    import time

    class _OlmusSurec:
        returncode = 1

    basla = time.monotonic()

    assert await browser_verify._wait_until_serving("http://127.0.0.1:9/", _OlmusSurec()) is False
    assert time.monotonic() - basla < 2


async def test_dev_sunucusu_kapanirken_cocuk_surecler_de_olur():
    import asyncio
    import os
    import sys

    if os.name != "posix":
        return
    surec = await asyncio.create_subprocess_exec(
        "sh",
        "-c",
        "sleep 300 & echo $!; wait",
        stdout=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    assert surec.stdout is not None
    cocuk = int((await surec.stdout.readline()).strip())

    await browser_verify._stop_server(surec)
    await asyncio.sleep(0.2)

    try:
        os.kill(cocuk, 0)
    except ProcessLookupError:
        return
    os.kill(cocuk, 9)  # temizlik: test başarısız
    raise AssertionError(f"yetim çocuk süreç yaşıyor ({sys.platform})")
