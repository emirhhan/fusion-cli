"""Dosya yazan araçlar alt ajanın `write_scope`'unu aşamaz (T1-08).

Ölçüldü (29 Ekim): `extract_archive`, `download_file`, `browser_screenshot`,
`browser_mirror`, `desktop_screenshot` ve `scaffold_web` yolu `resolve_path` ile
çözüyordu; yazma alanı kısıtlı bir alt ajan bu araçlarla alanı dışına dosya
bırakabiliyordu. Hepsi artık `writable_path` kapısından geçer.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from fusion_cli.core.browser_session import BrowserSession
from fusion_cli.core.errors import PathAccessError
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import archive, browser, desktop_screen, download, scaffold_tool


def _kapsamli(tmp_path: Path) -> tuple[ToolContext, Path, Path]:
    izinli = tmp_path / "izinli"
    yasak = tmp_path / "yasak"
    izinli.mkdir()
    yasak.mkdir()
    return ToolContext(root=tmp_path, write_scope=(izinli,)), izinli, yasak


def _zip(yol: Path) -> Path:
    with zipfile.ZipFile(yol, "w") as arsiv:
        arsiv.writestr("a.txt", "merhaba")
    return yol


class _SahteSayfa:
    url = "https://ornek.test/"

    async def screenshot(self, *, path: str, full_page: bool) -> None:
        del full_page
        Path(path).write_bytes(b"PNG")  # noqa: ASYNC240


def _tarayicili(tmp_path: Path) -> tuple[ToolContext, Path, Path]:
    _context, izinli, yasak = _kapsamli(tmp_path)
    oturum = BrowserSession()
    oturum.page = _SahteSayfa()
    return ToolContext(root=tmp_path, write_scope=(izinli,), browser=oturum), izinli, yasak


async def test_arsiv_alan_disina_acilmaz(tmp_path):
    context, izinli, yasak = _kapsamli(tmp_path)
    arsiv = _zip(izinli / "paket.zip")

    with pytest.raises(PathAccessError, match="yazma alanı dışında"):
        await archive.extract_archive({"path": str(arsiv), "dest": str(yasak)}, context)

    assert list(yasak.iterdir()) == []


async def test_arsiv_alan_icine_acilir(tmp_path):
    context, izinli, _yasak = _kapsamli(tmp_path)
    arsiv = _zip(izinli / "paket.zip")

    sonuc = await archive.extract_archive({"path": str(arsiv), "dest": str(izinli / "ac")}, context)

    assert sonuc.ok
    assert (izinli / "ac" / "a.txt").read_text() == "merhaba"


async def test_indirme_alan_disina_yazmaz(tmp_path):
    context, _izinli, yasak = _kapsamli(tmp_path)

    with pytest.raises(PathAccessError, match="yazma alanı dışında"):
        await download.download_file(
            {"url": "https://ornek.test/x.png", "path": str(yasak / "x.png")}, context
        )


async def test_tarayici_ekran_goruntusu_alan_disina_yazmaz(tmp_path):
    context, _izinli, yasak = _tarayicili(tmp_path)

    with pytest.raises(PathAccessError, match="yazma alanı dışında"):
        await browser.browser_screenshot({"path": str(yasak / "s.png")}, context)
    assert not (yasak / "s.png").exists()


async def test_tarayici_ayna_alan_disina_yazmaz(tmp_path):
    context, _izinli, yasak = _tarayicili(tmp_path)

    with pytest.raises(PathAccessError, match="yazma alanı dışında"):
        await browser.browser_mirror({"path": str(yasak / "ayna")}, context)
    assert not (yasak / "ayna").exists()


def test_masaustu_ekran_goruntusu_alan_disina_yazmaz(tmp_path, monkeypatch):
    context, _izinli, yasak = _kapsamli(tmp_path)
    monkeypatch.setattr(desktop_screen, "_mac_only", lambda: "")

    with pytest.raises(PathAccessError, match="yazma alanı dışında"):
        desktop_screen.desktop_screenshot({"path": str(yasak / "m.png")}, context)


def test_iskele_alan_disina_yazmaz(tmp_path):
    context, _izinli, yasak = _kapsamli(tmp_path)

    with pytest.raises(PathAccessError, match="yazma alanı dışında"):
        scaffold_tool.scaffold_web({"path": str(yasak / "site")}, context)
    assert not (yasak / "site").exists()


def test_kapsam_yoksa_iskele_eskisi_gibi_yazar(tmp_path):
    context = ToolContext(root=tmp_path)

    sonuc = scaffold_tool.scaffold_web({"path": "site"}, context)

    assert sonuc.ok and (tmp_path / "site" / "tokens.css").exists()
