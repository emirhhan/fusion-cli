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

import pytest

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


def test_surum_tek_kaynaktan_gelir():
    """`fusion version` ile paket sürümü AYNI olmalı.

    Gerçek hata: pyproject 0.3.0a1 derken `__init__` 0.2.0.dev0'da kalmıştı ve
    `fusion version` eski sürümü basıyordu. İki yerde elle tutulan sürüm zamanla
    ayrışır; hata raporlarında yanlış sürüm görünür.
    """
    from importlib.metadata import version

    import fusion_cli

    assert fusion_cli.__version__ == version("fusion-cli")


# --- README kodla ayrışmasın ------------------------------------------------- #


def _readme() -> str:
    from pathlib import Path

    return (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")


def test_readme_kurulum_komutlarinda_yer_tutucu_yoktur():
    """Kopyalanabilir olmayan komut, komut değildir.

    `<depo-adresi>` gibi bir yer tutucu kullanıcıyı ilk adımda durdurur.
    """
    metin = _readme()

    for tutucu in ("<depo-adresi>", "<repo-url>", "TODO", "XXX"):
        assert tutucu not in metin, f"README'de yer tutucu var: {tutucu}"


def test_readme_kademe_tablosu_defaults_ile_uyumlu():
    """README'deki model tablosu `defaults.yaml`'dan AYRIŞMAMALI.

    İki kaynak elle senkron tutulursa zamanla ayrışır ve README yalan söyler;
    bu proje o hatayı bir kez yaşadı (mükerrer `tiers` bloğu).
    """
    from fusion_cli.config.loader import load_config

    metin = _readme()
    for kademe in load_config().tiers:
        assert f"`{kademe.name}`" in metin, f"README'de {kademe.name} kademesi yok"


def test_readme_hem_kullanici_hem_gelistirici_kurulumunu_anlatir():
    metin = _readme()

    assert "./setup.sh" in metin
    assert "--dev" in metin
    assert "install.ps1" in metin, "Windows yolu belgelenmemiş"


def test_readme_anahtar_konumunu_tek_yer_olarak_yazar():
    """İki .env karışıklığı belgeyle de çözülmeli."""
    metin = _readme()

    assert ".config/fusion-cli/.env" in metin
    assert "APPDATA" in metin


# --- Wheel smoke testi ------------------------------------------------------- #


@pytest.mark.slow
def test_temiz_wheel_ortaminda_cli_calisir(tmp_path):
    """Wheel'den kurulan sürüm ilk komutta çalışmalı.

    Editable kurulumda çalışan kod, wheel'de eksik bir veri dosyası yüzünden
    çökebiliyor: prompt dosyaları import anında okunuyor. Bu testi geliştirici
    makinesinde geçmek yetmez, gerçek wheel kurulumunda geçmeli.
    """
    import subprocess
    import sys
    import venv
    from pathlib import Path

    kok = Path(__file__).resolve().parents[1]
    tekerlek_dizini = tmp_path / "wheel"
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", str(kok), "--no-deps", "-w", str(tekerlek_dizini)],
        check=True,
        capture_output=True,
    )
    tekerlekler = list(tekerlek_dizini.glob("fusion_cli-*.whl"))
    assert tekerlekler, "wheel üretilemedi"

    ortam = tmp_path / "venv"
    venv.create(ortam, with_pip=True)
    pip = ortam / ("Scripts" if sys.platform == "win32" else "bin") / "pip"
    fusion = ortam / ("Scripts" if sys.platform == "win32" else "bin") / "fusion"
    subprocess.run([str(pip), "install", "-q", str(tekerlekler[0])], check=True)

    for argumanlar in (["version"], ["--help"], ["doctor"]):
        sonuc = subprocess.run(
            [str(fusion), *argumanlar], capture_output=True, text=True, timeout=120
        )
        # doctor yapılandırma eksikse 1 döner; çökmesi (>1) kabul edilemez.
        assert sonuc.returncode in (0, 1), f"fusion {argumanlar}: {sonuc.stderr[:400]}"
