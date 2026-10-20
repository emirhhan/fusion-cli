"""Otomatik Chrome kurulumunu (chrome_autoinstall.py) Fusion'a bağlar. Tek seferlik, güvenle tekrar çalışır.

Kullanım (depo kökünde): python3 scripts/chrome_otomatik_kur_bagla.py
"""

from __future__ import annotations

from pathlib import Path

KOK = Path(__file__).resolve().parents[1]


def degistir(yol: str, eski: str, yeni: str) -> None:
    dosya = KOK / yol
    metin = dosya.read_text(encoding="utf-8")
    if yeni in metin:
        print(f"zaten uygulanmış: {yol}")
        return
    if eski not in metin:
        raise SystemExit(f"beklenen metin bulunamadı: {yol}\n---\n{eski}")
    dosya.write_text(metin.replace(eski, yeni, 1), encoding="utf-8")
    print(f"güncellendi: {yol}")


SESSION = "src/fusion_cli/appserver/session.py"
degistir(
    SESSION,
    "installer=lambda: asyncio.to_thread(begin_install),",
    "installer=auto_install_async,",
)
degistir(
    SESSION,
    'kurulum = await asyncio.to_thread(begin_install)',
    "kurulum = await auto_install_async()",
)
degistir(
    SESSION,
    "from .chrome_install import begin_install, install_status\n",
    "from .chrome_autoinstall import auto_install_async\nfrom .chrome_install import install_status\n",
)
degistir(
    "src/fusion_cli/appserver/chrome_bridge.py",
    "            await self._installer()\n            if await",
    '            sonuc = await self._installer()\n'
    '            if sonuc.get("asama") == "izin_gerekli":\n'
    '                raise ConnectionError(str(sonuc.get("metin")))\n'
    "            if await",
)
degistir(
    "app/src/settings/ChromeBrowser.tsx",
    "      setSteps(result.adimlar ?? []);",
    '      setSteps(result.asama === "yuklendi" ? [] : result.adimlar ?? []);\n'
    '      if (result.asama === "izin_gerekli" || result.asama === "elle") setError(result.metin ?? "");',
)
degistir(
    "app/src/settings/ChromeBrowser.tsx",
    "  adimlar?: string[];\n",
    '  adimlar?: string[];\n  asama?: "yuklendi" | "izin_gerekli" | "elle" | "desteklenmiyor" | "hata";\n',
)
print("Bitti. Şimdi Claude'a 'bağlandı' yaz.")
