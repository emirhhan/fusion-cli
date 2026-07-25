"""Paketleme — kodun okuduğu veri dosyaları wheel'e giriyor mu.

Gerçek hata: `engines/agent/prompts/*` ve `engines/fusion/prompts/*` package-data'da
yoktu. Kod bu dosyaları import anında okuyor (`SYSTEM_PROMPT = ...read_text()`), yani
wheel'den kurulan bir sürüm ilk komutta çökerdi. Depoda `pip install -e .` ile
çalışıldığı için yıllarca fark edilmemişti.

Bu test dosya sisteminden gider: `src/` altındaki her veri dosyası için pyproject'te
onu kapsayan bir package-data girdisi olmalı.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

_KOK = Path(__file__).resolve().parent.parent
_SRC = _KOK / "src" / "fusion_cli"
#: Pakete girmesi gerekmeyen dosyalar (derleme çıktısı ve işletim sistemi çöpü).
_YOKSAY = {".pyc", ".pyo"}
_YOKSAY_AD = {".DS_Store"}


def _veri_dosyalari() -> list[Path]:
    """Kod olmayan, pakete girmesi gereken dosyalar."""
    return [
        yol
        for yol in _SRC.rglob("*")
        if yol.is_file()
        and yol.suffix not in _YOKSAY
        and yol.name not in _YOKSAY_AD
        and yol.suffix != ".py"
        and "__pycache__" not in yol.parts
        and "egg-info" not in str(yol)
    ]


def _package_data() -> dict[str, list[str]]:
    with (_KOK / "pyproject.toml").open("rb") as dosya:
        veri = tomllib.load(dosya)
    tool = veri.get("tool", {}).get("setuptools", {})
    return tool.get("package-data", {})


def test_kodun_okudugu_her_veri_dosyasi_paketleniyor():
    kurallar = _package_data()
    kapsanmayan: list[str] = []

    for yol in _veri_dosyalari():
        goreli = yol.relative_to(_SRC)
        paket = "fusion_cli" + "".join(f".{parca}" for parca in goreli.parts[:-1])
        # Girdi ya dosyanın kendi paketinde ya da üst pakette "altdizin/*" olarak olabilir.
        kapsandi = False
        for anahtar, desenler in kurallar.items():
            if not paket.startswith(anahtar):
                continue
            kalan = goreli.parts[len(anahtar.split(".")) - 1 :]
            aday = "/".join(kalan)
            if any(Path(aday).match(desen) for desen in desenler):
                kapsandi = True
                break
        if not kapsandi:
            kapsanmayan.append(str(goreli))

    assert not kapsanmayan, (
        "pyproject.toml package-data bu dosyaları kapsamıyor; wheel'den kurulum "
        f"çalışmaz: {kapsanmayan}"
    )


def test_sistem_promptu_gercekten_var():
    """En kritik dosya: yoksa agent motoru import edilemez."""
    assert (_SRC / "engines" / "agent" / "prompts" / "system.md").is_file()
