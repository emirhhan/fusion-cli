"""Depo haritası: içe aktarma grafı, bayt kararlılığı, zaman sınırı (yol haritası 8. adım).

Ölçüldü (30 Ekim, fusion-cli deposunun kendisi): eski sayım haritası `result`, `config`, `text`
gibi genel adlarla ve test dosyalarıyla doluydu (3.000 karakterde 74 satırın ~%55'i test
dosyası; en çok içe aktarılan 20 dosyadan yalnız 2'si görünüyordu). İçe aktarma grafıyla
sıralanınca test oranı 0, aynı 20 dosyadan 16'sı görünüyor.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.core import repo_map
from fusion_cli.core.repo_imports import (
    ModuleIndex,
    build_graph,
    extract_imports,
)
from fusion_cli.core.repo_map import (
    build_repo_map,
    build_repo_map_report,
    is_test_path,
    register_definition_extractor,
)


@pytest.fixture(autouse=True)
def _temiz_onbellek():
    repo_map._CACHE.clear()
    yield
    repo_map._CACHE.clear()
    repo_map._EXTRACTORS.clear()


def _yaz(kok: Path, dosyalar: dict[str, str]) -> Path:
    for yol, icerik in dosyalar.items():
        hedef = kok / yol
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_text(icerik, "utf-8")
    return kok


# --- çıkarım ----------------------------------------------------------------------


def test_python_icaktarmalari_adlariyla_cikarilir():
    kaynak = (
        "import os, json as j\n"
        "from a.b import c, d as e\n"
        "from . import kardes\n"
        "from ..ust import (\n    x,  # yorum\n    y,\n)\n"
        "from p import *\n"
    )
    refler = {(r.spec, r.names, r.level) for r in extract_imports(".py", kaynak)}

    assert ("os", (), 0) in refler and ("json", (), 0) in refler
    assert ("a.b", ("c", "d"), 0) in refler
    assert ("", ("kardes",), 1) in refler
    assert ("ust", ("x", "y"), 2) in refler
    assert ("p", (), 0) in refler


def test_js_ts_icaktarmalari_adlari_ve_yollari_cikarilir():
    kaynak = (
        "import Varsayilan, { a, b as c, type T } from './x'\n"
        "import * as ns from '../y'\n"
        "import './yan-etki'\n"
        "export { z } from './z'\n"
        "const { q, r } = require('./w')\n"
        "const m = await import('./dinamik')\n"
        "import react from 'react'\n"
    )
    refler = {r.spec: r.names for r in extract_imports(".ts", kaynak)}

    assert refler["./x"] == ("a", "b", "T")
    assert refler["../y"] == ()
    assert refler["./yan-etki"] == () and refler["./dinamik"] == ()
    assert refler["./z"] == ("z",)
    assert refler["./w"] == ("q", "r")
    assert refler["react"] == ()


def test_php_use_ve_require_cikarilir():
    kaynak = (
        "<?php\nuse App\\Models\\User;\nuse App\\Http\\{Kontrol, Yardim as Y};\n"
        "require_once __DIR__ . '/inc/ayar.php';\n$f = function () use ($x) {};\n"
    )
    refler = {(r.spec, r.names) for r in extract_imports(".php", kaynak)}

    assert ("App\\Models\\User", ("User",)) in refler
    assert ("App\\Http\\Kontrol", ("Kontrol",)) in refler
    assert ("App\\Http\\Yardim", ("Yardim",)) in refler
    assert ("/inc/ayar.php", ()) in refler
    assert not any(r.spec == "x" for r in extract_imports(".php", kaynak))


# --- çözümleme ve graf --------------------------------------------------------------


def _graf(dosyalar: dict[str, str]):
    imports = {
        yol: extract_imports(Path(yol).suffix, metin)
        for yol, metin in dosyalar.items()
        if Path(yol).suffix in {".py", ".ts", ".tsx", ".js", ".php"}
    }
    return build_graph(imports, ModuleIndex.build(imports), is_test=is_test_path)


def test_python_mutlak_ve_goreli_cozumleme():
    graf = _graf(
        {
            "src/pkg/__init__.py": "",
            "src/pkg/cekirdek.py": "def temel(): ...\n",
            "src/pkg/alt/__init__.py": "",
            "src/pkg/alt/is.py": "from pkg.cekirdek import temel\nfrom .. import cekirdek\n",
            "src/pkg/kullanan.py": "from .cekirdek import temel\nimport pkg.alt.is\n",
        }
    )

    assert graf.fan_in["src/pkg/cekirdek.py"] == 2
    assert graf.named_in[("src/pkg/cekirdek.py", "temel")] == 2
    assert graf.fan_in["src/pkg/alt/is.py"] == 1


def test_standart_kutuphane_adi_yerel_dosyaya_baglanmaz():
    """`from typing import X` bir `typing.py`'ye (yerel `types.py` gibi) bağlanmamalı."""
    graf = _graf(
        {
            "alt/types.py": "class A: ...\n",
            "alt/kullan.py": "from types import SimpleNamespace\nimport typing\n",
        }
    )

    assert graf.fan_in.get("alt/types.py", 0) == 0


def test_js_goreli_alias_ve_index_cozumleme():
    graf = _graf(
        {
            "src/a.ts": "export const a = 1\n",
            "src/ui/index.ts": "export const u = 1\n",
            "src/ui/Dugme.tsx": "export const Dugme = () => 1\n",
            "src/sayfa.ts": (
                "import { a } from './a.js'\nimport { u } from './ui'\n"
                "import { Dugme } from '@/ui/Dugme'\nimport r from 'react'\n"
            ),
        }
    )

    assert graf.fan_in["src/a.ts"] == 1
    assert graf.fan_in["src/ui/index.ts"] == 1
    assert graf.fan_in["src/ui/Dugme.tsx"] == 1
    assert graf.named_in[("src/ui/Dugme.tsx", "Dugme")] == 1


def test_php_sinif_ve_require_cozumleme():
    graf = _graf(
        {
            "app/Models/User.php": "<?php class User {}\n",
            "inc/ayar.php": "<?php\n",
            "app/Kontrol.php": (
                "<?php\nuse App\\Models\\User;\nrequire_once __DIR__ . '/../inc/ayar.php';\n"
            ),
        }
    )

    assert graf.fan_in["app/Models/User.php"] == 1
    assert graf.fan_in["inc/ayar.php"] == 1


def test_test_dosyalari_ve_kendi_kendine_icaktarma_sayilmaz():
    graf = _graf(
        {
            "cekirdek.py": "def f(): ...\nimport cekirdek\n",
            "tests/test_c.py": "from cekirdek import f\n",
            "uygulama.py": "from cekirdek import f\n",
        }
    )

    assert graf.fan_in["cekirdek.py"] == 1
    assert graf.named_in[("cekirdek.py", "f")] == 1


# --- sıralama -------------------------------------------------------------------------


def test_cok_icaktarilan_dosya_ve_adlar_onde_testler_sonda(tmp_path):
    """Genel ad (`config`) test dosyasında çok geçse de çekirdek sembolün önüne geçemez."""
    dosyalar = {
        "cekirdek/tipler.py": "class Mesaj: ...\ndef yardimci(): ...\n",
        "cekirdek/nadir.py": "def tek(): ...\n",
        "tests/test_a.py": (
            "from cekirdek.tipler import Mesaj\n" + "def config():\n    pass\n" + "config()\n" * 50
        ),
    }
    for sira in range(4):
        dosyalar[f"uyg/m{sira}.py"] = "from cekirdek.tipler import Mesaj\nMesaj()\n"
    harita = build_repo_map(_yaz(tmp_path, dosyalar), budget_chars=3_000).splitlines()

    assert harita[0] == "cekirdek/tipler.py: Mesaj"
    assert harita.index("cekirdek/tipler.py: Mesaj") < harita.index("cekirdek/nadir.py: tek")
    assert harita.index("cekirdek/nadir.py: tek") < harita.index("tests/test_a.py: config")


def test_graf_olmayan_dil_eski_sayima_duser(tmp_path):
    """Go/Rust gibi içe aktarma çıkarımı olmayan dillerde ad sayımı kullanılır (tavanlı)."""
    _yaz(
        tmp_path,
        {
            "a.go": "func Cok() {}\nfunc Az() {}\n",
            "b.go": "func x() { Cok(); Cok(); Cok() }\n",
        },
    )

    satirlar = build_repo_map(tmp_path, budget_chars=1_000).splitlines()

    assert satirlar.index("a.go: Cok") < satirlar.index("a.go: Az")


def test_dosya_basina_sinir_puanlamadan_sonra_uygulanir(tmp_path):
    """İçe aktarılan ad dosyada 12. tanımdan sonra olsa bile haritaya girer."""
    govde = "".join(f"def f{i}(): ...\n" for i in range(30)) + "def onemli(): ...\n"
    _yaz(
        tmp_path,
        {"buyuk.py": govde, "kullan.py": "from buyuk import onemli\nonemli()\n"},
    )

    assert "buyuk.py: onemli" in build_repo_map(tmp_path, budget_chars=3_000)


# --- bayt kararlılığı -------------------------------------------------------------------


def test_ayni_depo_ayni_bayt_ciktisi_verir(tmp_path):
    for sira in range(8):
        _yaz(
            tmp_path,
            {
                f"m{sira}.py": (
                    f"from m{(sira + 1) % 8} import f{(sira + 1) % 8}\ndef f{sira}(): ...\n"
                )
            },
        )

    ilk = build_repo_map(tmp_path, budget_chars=3_000)
    repo_map._CACHE.clear()
    ikinci = build_repo_map(tmp_path, budget_chars=3_000)

    assert ilk and ilk == ikinci
    assert ilk.encode() == ikinci.encode()


def test_dosya_listesi_sirasi_cikti_degistirmez(tmp_path, monkeypatch):
    _yaz(tmp_path, {f"m{i}.py": f"def f{i}(): ...\n" for i in range(6)})
    gercek = repo_map.project_files

    ileri = build_repo_map(tmp_path, budget_chars=3_000)
    repo_map._CACHE.clear()
    monkeypatch.setattr(
        repo_map, "project_files", lambda *a, **k: (gercek(*a, **k)[0][::-1], False)
    )
    geri = build_repo_map(tmp_path, budget_chars=3_000)

    assert ileri == geri


# --- zaman ve dosya sınırı -----------------------------------------------------------------


def test_zaman_siniri_asilinca_kismi_harita_ve_onbellekle_kararli(tmp_path, monkeypatch):
    _yaz(tmp_path, {f"m{i:02d}.py": f"def f{i}(): ...\n" for i in range(10)})
    sayac = iter(range(10_000))
    monkeypatch.setattr(repo_map, "_simdi", lambda: next(sayac) * 0.1)

    sonuc = build_repo_map_report(tmp_path, budget_chars=3_000, time_limit_s=0.35)
    tekrar = build_repo_map_report(tmp_path, budget_chars=3_000, time_limit_s=0.35)

    assert sonuc.stats.time_limited and sonuc.stats.partial
    assert 0 < sonuc.stats.files < 10
    assert sonuc.text.startswith("(zaman sınırı aşıldı: harita kısmi)")
    assert tekrar.stats.cached and tekrar.text == sonuc.text


def test_zaman_asiminda_once_kaynak_sonra_test_okunur(tmp_path, monkeypatch):
    _yaz(
        tmp_path,
        {
            "tests/test_a.py": "def test_a(): ...\n",
            "kaynak.py": "def gercek(): ...\n",
            "derin/ic/ic/d.py": "def derin(): ...\n",
        },
    )
    sayac = iter(range(10_000))
    monkeypatch.setattr(repo_map, "_simdi", lambda: next(sayac) * 0.1)

    harita = build_repo_map(tmp_path, budget_chars=3_000, time_limit_s=0.15)

    assert "kaynak.py: gercek" in harita
    assert "test_a" not in harita


def test_buyuk_dosya_okunmaz(tmp_path):
    _yaz(
        tmp_path,
        {
            "paket.min.js": "function minify() {}\n" + "x" * (repo_map._MAX_FILE_BYTES + 1),
            "kod.py": "def gercek(): ...\n",
        },
    )

    harita = build_repo_map(tmp_path, budget_chars=3_000)

    assert "gercek" in harita and "minify" not in harita


# --- ölçüm izi ----------------------------------------------------------------------------


def test_rapor_olcum_alanlarini_doldurur(tmp_path):
    _yaz(
        tmp_path,
        {
            "a.py": "def a(): ...\n",
            "b.py": "from a import a\ndef b(): ...\n",
            "tests/test_b.py": "from b import b\n",
        },
    )

    ilk = build_repo_map_report(tmp_path, budget_chars=3_000)
    ikinci = build_repo_map_report(tmp_path, budget_chars=3_000)

    assert ilk.stats.files == 3 and ilk.stats.candidates == 3
    assert ilk.stats.symbols == 2 and ilk.stats.shown == 2
    # Kenar sayısı test olmayan içe aktarmalardır (test -> b kenarı sayılmaz).
    assert ilk.stats.edges == 1 and ilk.stats.chars == len(ilk.text)
    assert not ilk.stats.partial and not ilk.stats.cached and ikinci.stats.cached


def test_butce_sifir_haritayi_kapatir(tmp_path):
    _yaz(tmp_path, {"a.py": "def a(): ...\n"})

    assert build_repo_map(tmp_path, budget_chars=0) == ""


# --- eklenti noktası --------------------------------------------------------------------


def test_kayitli_cikarici_regexin_yerine_gecer_none_donerse_regexe_duser(tmp_path):
    _yaz(tmp_path, {"a.py": "def regex_adi(): ...\n", "b.py": "def baska(): ...\n"})
    register_definition_extractor(
        ".py", lambda kaynak: ["eklenti_adi"] if "regex_adi" in kaynak else None
    )

    harita = build_repo_map(tmp_path, budget_chars=3_000)

    assert "a.py: eklenti_adi" in harita and "regex_adi" not in harita
    assert "b.py: baska" in harita


def test_bozuk_cikarici_haritayi_dusurmez(tmp_path):
    _yaz(tmp_path, {"a.py": "def a(): ...\n"})

    def patla(kaynak):
        raise RuntimeError("eklenti bozuk")

    register_definition_extractor(".py", patla)

    assert "a.py: a" in build_repo_map(tmp_path, budget_chars=3_000)


def test_eklenti_yokken_davranis_ayni_entry_point_yuklenir(tmp_path, monkeypatch):
    class Nokta:
        name = ".py"

        def load(self):
            return lambda kaynak: ["ep_adi"]

    monkeypatch.setattr(repo_map, "_plugins_loaded", False)
    monkeypatch.setattr(repo_map.importlib.metadata, "entry_points", lambda group: [Nokta()])
    _yaz(tmp_path, {"a.py": "def a(): ...\n"})

    assert "a.py: ep_adi" in build_repo_map(tmp_path, budget_chars=3_000)


def test_entry_point_hatasi_regex_yolunu_korur(tmp_path, monkeypatch):
    monkeypatch.setattr(repo_map, "_plugins_loaded", False)

    def patla(group):
        raise OSError("metadata okunamadı")

    monkeypatch.setattr(repo_map.importlib.metadata, "entry_points", patla)
    _yaz(tmp_path, {"a.py": "def a(): ...\n"})

    assert "a.py: a" in build_repo_map(tmp_path, budget_chars=3_000)
