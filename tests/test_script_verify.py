"""`package.json` betik yolları — kardeş projeleri yanlış bağlama hatası.

Ölçüldü (canlı koşu): kullanıcı "bağlı projeleri tek yerden kontrol edebileyim"
dedi ve model şu betiği yazdı:

    "dev:ai": "sh -c 'cd ../GATE-AI && npm install && npm run dev'"

`../GATE-AI` dizini VAR ama içinde `package.json` YOK — uygulama `GATE-AI/web`
altında. Betik çalıştığı anda patlar. Derleme kapısı bunu göremez çünkü
`npm run build` o betiği çalıştırmaz; kullanıcı hatayı ancak `npm run start:all`
dediğinde bulur.
"""

from __future__ import annotations

import json
from pathlib import Path

from fusion_cli.engines.agent.script_verify import ScriptPathVerifier


def _proje(root: Path, scripts: dict[str, str]) -> None:
    (root / "package.json").write_text(json.dumps({"scripts": scripts}), encoding="utf-8")


def _kardes(root: Path, ad: str, scripts: dict[str, str] | None) -> Path:
    hedef = root.parent / ad
    hedef.mkdir(parents=True, exist_ok=True)
    if scripts is not None:
        (hedef / "package.json").write_text(json.dumps({"scripts": scripts}), encoding="utf-8")
    return hedef


async def test_paketsiz_dizine_npm_run_yakalanir(tmp_path):
    kok = tmp_path / "ana"
    kok.mkdir()
    _kardes(kok, "yan", None)  # dizin var, package.json yok
    _proje(kok, {"dev:yan": "sh -c 'cd ../yan && npm install && npm run dev'"})

    sonuc = await ScriptPathVerifier(kok).verify()

    assert sonuc.ok is False
    assert "package.json yok" in sonuc.findings[0]


async def test_olmayan_dizin_yakalanir(tmp_path):
    kok = tmp_path / "ana"
    kok.mkdir()
    _proje(kok, {"dev:yok": "npm --prefix ../hicyok run dev"})

    sonuc = await ScriptPathVerifier(kok).verify()

    assert sonuc.ok is False
    assert "olmayan bir dizini" in sonuc.findings[0]


async def test_olmayan_betik_yakalanir(tmp_path):
    kok = tmp_path / "ana"
    kok.mkdir()
    _kardes(kok, "yan", {"build": "x"})
    _proje(kok, {"dev:yan": "npm --prefix ../yan run dev"})

    sonuc = await ScriptPathVerifier(kok).verify()

    assert sonuc.ok is False
    assert "böyle bir betik yok" in sonuc.findings[0]
    assert "build" in sonuc.findings[0], "var olan betikler gösterilmeli"


async def test_dogru_baglanti_gecer(tmp_path):
    kok = tmp_path / "ana"
    kok.mkdir()
    _kardes(kok, "yan", {"dev": "next dev"})
    _proje(kok, {"dev:yan": "npm --prefix ../yan run dev"})

    assert (await ScriptPathVerifier(kok).verify()).ok is True


async def test_npm_install_betik_sayilmaz(tmp_path):
    """`npm install` bir betik adı değildir; yokluğu hata değildir."""
    kok = tmp_path / "ana"
    kok.mkdir()
    _kardes(kok, "yan", {"dev": "x"})
    _proje(kok, {"kur": "sh -c 'cd ../yan && npm install'"})

    assert (await ScriptPathVerifier(kok).verify()).ok is True


async def test_package_json_yoksa_kapi_susar(tmp_path):
    assert (await ScriptPathVerifier(tmp_path).verify()).ok is True


async def test_kendi_betikleri_yol_icermiyorsa_gecer(tmp_path):
    kok = tmp_path / "ana"
    kok.mkdir()
    _proje(kok, {"dev": "next dev", "build": "next build"})

    assert (await ScriptPathVerifier(kok).verify()).ok is True
