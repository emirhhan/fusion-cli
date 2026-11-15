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


async def test_cok_cd_li_betikte_her_cd_kendi_dizininde_denetlenir(tmp_path):
    """Ölçüldü (29 Ekim): ilk `cd`'nin `rest`'i satır sonuna dek uzanıyor, `cd ../api`
    sonrası `npm run start:dev` `web/` içinde aranıp yanlış bulgu veriyordu (A4-13)."""
    kok = tmp_path / "ana"
    (kok / "web").mkdir(parents=True)
    (kok / "api").mkdir()
    (kok / "web" / "package.json").write_text('{"scripts": {"build": "x"}}', encoding="utf-8")
    (kok / "api" / "package.json").write_text('{"scripts": {"start:dev": "x"}}', encoding="utf-8")
    _proje(kok, {"hepsi": "cd web && npm run build && cd ../api && npm run start:dev"})

    sonuc = await ScriptPathVerifier(kok).verify()

    assert sonuc.ok is True, sonuc.findings


async def test_cok_cd_li_betikte_gercek_eksik_hala_yakalanir(tmp_path):
    kok = tmp_path / "ana"
    (kok / "web").mkdir(parents=True)
    (kok / "api").mkdir()
    (kok / "web" / "package.json").write_text('{"scripts": {"build": "x"}}', encoding="utf-8")
    (kok / "api" / "package.json").write_text('{"scripts": {"start": "x"}}', encoding="utf-8")
    _proje(kok, {"hepsi": "cd web && npm run build && cd ../api && npm run start:dev"})

    sonuc = await ScriptPathVerifier(kok).verify()

    assert sonuc.ok is False
    assert "api" in sonuc.findings[0] and "start:dev" in sonuc.findings[0]


async def test_npm_alt_komutlari_betik_adi_sayilmaz(tmp_path):
    kok = tmp_path / "ana"
    (kok / "web").mkdir(parents=True)
    (kok / "web" / "package.json").write_text('{"scripts": {"dev": "x"}}', encoding="utf-8")
    _proje(
        kok,
        {
            "a": "cd web && npm i && npm audit && npm exec tsc && npm update",
            "b": "cd web && npm run-script dev",
            "c": "cd web && npm run-script yok",
        },
    )

    sonuc = await ScriptPathVerifier(kok).verify()

    assert len(sonuc.findings) == 1, sonuc.findings
    assert "'c'" in sonuc.findings[0] and "yok" in sonuc.findings[0]
