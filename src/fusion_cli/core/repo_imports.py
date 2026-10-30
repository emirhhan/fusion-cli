"""İçe aktarma grafı — depo haritasının sıralama sinyali.

Harita yalnız "bu isim kaç kez geçiyor" sayısıyla sıralanınca, her yerde geçen genel
adlar (`config`, `result`, `text`) önemli sembollerin önüne geçiyordu. Burada Aider'ın
dosya grafiğinin yalın karşılığı kurulur: hangi dosya hangi dosyayı içe aktarıyor, ve
hangi ADLARI adıyla içe aktarıyor. İki sayı çıkar:

- `fan_in[dosya]`: o dosyayı içe aktaran (test olmayan) dosya sayısı;
- `named_in[(dosya, ad)]`: o adı AÇIKÇA (`from x import ad`, `import {ad} from`,
  `use A\\B\\Ad`) içe aktaran (test olmayan) dosya sayısı.

Çözümleme REGEX'tir; tree-sitter yok (bkz. `repo_map` başlığı). Desteklenen: Python
(`import`, `from … import`, göreli noktalar), JS/TS (`import … from`, `export … from`,
`require`, dinamik `import()`, göreli yol ve `@/`/`~/` takma adı), PHP (`use`,
`require`/`include`). Çözülemeyen belirteç (paket adı, standart kütüphane, dinamik yol)
sessizce atlanır: grafik eksik olabilir, YANLIŞ kenar üretmemeye çalışır.

Sonuç belirleyicidir: aynı dosya kümesi aynı grafı verir (kümeler sıralı gezilir, belirsiz
eşleşmede en yakın dizin, sonra yol sırası kazanır) — harita önek kararlılığı buna bağlı.
"""

from __future__ import annotations

import posixpath
import re
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

__all__ = [
    "GRAPH_SUFFIXES",
    "ImportGraph",
    "ImportRef",
    "ModuleIndex",
    "build_graph",
    "extract_imports",
]

#: İçe aktarma çıkarımı olan uzantılar. Diğer dillerde harita eski sayım yoluna döner.
GRAPH_SUFFIXES = frozenset({".py", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".php"})

_JS_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
#: `./a.js` ifadesi TS kaynağında `a.ts`'yi kasteder (ESM yazım kuralı).
_JS_JS_TO_TS = {".js": (".ts", ".tsx"), ".jsx": (".tsx",), ".mjs": (".mts",), ".cjs": (".cts",)}
#: Kaynak kök dizinleri: `src/pkg/x.py` içindeki modül adı `pkg.x`'tir.
_SOURCE_ROOTS = frozenset({"src", "lib", "python"})
_ALIAS_PREFIXES = ("@/", "~/", "#/")
#: Kütüphane içe aktarımları yerel dosyayla karışmasın: `from typing import X` bir
#: `types.py`'ye bağlanmaz. Yalnız kökten başlayan tam eşleşme yerelde sayılır.
_STDLIB = frozenset(getattr(sys, "stdlib_module_names", ()))


@dataclass(frozen=True, slots=True)
class ImportRef:
    """Bir dosyanın tek içe aktarma bildirimi."""

    #: Ham modül/yol belirteci (`a.b`, `./x`, `App\Models\User`).
    spec: str
    #: Açıkça içe aktarılan adlar (yoksa boş: modülün tamamı).
    names: tuple[str, ...] = ()
    #: Python göreli içe aktarmada baştaki nokta sayısı.
    level: int = 0


# --------------------------------------------------------------------------- çıkarım

_PY_IMPORT = re.compile(
    r"^[ \t]*(?:from[ \t]+(?P<nokta>\.*)(?P<modul>[\w.]*)[ \t]+import[ \t]+"
    r"(?P<adlar>\([^)]*\)|[^\n]+)"
    r"|import[ \t]+(?P<duz>[\w.]+(?:[ \t]+as[ \t]+\w+)?"
    r"(?:[ \t]*,[ \t]*[\w.]+(?:[ \t]+as[ \t]+\w+)?)*))",
    re.MULTILINE,
)
#: JS/TS tek geçiş: `from '…'`, `import '…'`/`import('…')`, `require('…')`.
_JS_SPEC = re.compile(
    r"(?:\b(?P<from>from)\s*|\bimport\s*\(?\s*|\b(?P<req>require)\s*\(\s*)"
    r"['\"](?P<spec>[^'\"\n]+)['\"]"
)
_JS_DESTRUCT = re.compile(r"\{([^{}]*)\}\s*=\s*$")
#: `from` ifadesinin bildirim başlığını (import/export) geriye doğru ararken bakılan pencere.
_JS_CLAUSE_WINDOW = 600
_PHP_USE = re.compile(
    r"^[ \t]*use[ \t]+(?:function[ \t]+|const[ \t]+)?\\?([A-Za-z_][\w\\]*)"
    r"(?:\\\{([^}]*)\}|(?:[ \t]+as[ \t]+\w+)?[ \t]*[;,])",
    re.MULTILINE,
)
_PHP_REQUIRE = re.compile(
    r"\b(?:require|include)(?:_once)?\b[^'\"\n;]*?['\"](?P<spec>[^'\"\n]+\.php)['\"]"
)
_YORUM = re.compile(r"#[^\n]*")
_AD = re.compile(r"[A-Za-z_$][\w$]*")


def extract_imports(suffix: str, kaynak: str) -> list[ImportRef]:
    """Kaynaktaki içe aktarma bildirimlerini döndür; desteklenmeyen uzantıda boş."""
    if suffix == ".py":
        return _python_imports(kaynak)
    if suffix == ".php":
        return _php_imports(kaynak)
    if suffix in GRAPH_SUFFIXES:
        return _js_imports(kaynak)
    return []


def _python_imports(kaynak: str) -> list[ImportRef]:
    if "import" not in kaynak:
        return []
    bulunan: list[ImportRef] = []
    for eslesme in _PY_IMPORT.finditer(kaynak):
        duz = eslesme.group("duz")
        if duz is not None:
            for parca in duz.split(","):
                modul = parca.split()[0] if parca.split() else ""
                if modul:
                    bulunan.append(ImportRef(modul))
            continue
        govde = _YORUM.sub("", eslesme.group("adlar")).strip("() \t\r\n")
        secilen = tuple(
            dict.fromkeys(
                ad
                for parca in govde.replace("\n", " ").split(",")
                if (ad := parca.strip().split(" ")[0]) and ad != "*" and ad.isidentifier()
            )
        )
        bulunan.append(ImportRef(eslesme.group("modul"), secilen, len(eslesme.group("nokta"))))
    return bulunan


def _js_names(kume: str) -> tuple[str, ...]:
    """`a, b as c, type D` biçiminden SOL adları çıkar (varsayılan/ad alanı atılır)."""
    adlar: list[str] = []
    for parca in kume.split(","):
        kelimeler = [k for k in parca.replace(":", " as ").split() if k != "type"]
        if kelimeler and _AD.fullmatch(kelimeler[0]) and kelimeler[0] != "as":
            adlar.append(kelimeler[0])
    return tuple(dict.fromkeys(adlar))


def _js_imports(kaynak: str) -> list[ImportRef]:
    if "import" not in kaynak and "require" not in kaynak and "from" not in kaynak:
        return []
    bulunan: list[ImportRef] = []
    for eslesme in _JS_SPEC.finditer(kaynak):
        bas = eslesme.start()
        adlar: tuple[str, ...] = ()
        if eslesme.group("from"):
            # Bildirimin başlığı: en yakın önceki `import`/`export`. Yalnız süslü
            # parantezli adlar açıktır; `import X` / `* as ns` modül düzeyidir.
            pencere = max(0, bas - _JS_CLAUSE_WINDOW)
            baslik = max(kaynak.rfind("import", pencere, bas), kaynak.rfind("export", pencere, bas))
            kume = kaynak[baslik + 6 : bas] if baslik >= 0 else ""
            if "{" in kume and "}" in kume:
                adlar = _js_names(kume[kume.find("{") + 1 : kume.rfind("}")])
        elif eslesme.group("req"):
            oncesi = _JS_DESTRUCT.search(kaynak, max(0, bas - 300), bas)
            if oncesi:
                adlar = _js_names(oncesi.group(1))
        bulunan.append(ImportRef(eslesme.group("spec"), adlar))
    return bulunan


def _php_imports(kaynak: str) -> list[ImportRef]:
    if "use" not in kaynak and "require" not in kaynak and "include" not in kaynak:
        return []
    bulunan: list[ImportRef] = []
    for eslesme in _PHP_USE.finditer(kaynak):
        taban, grup = eslesme.group(1), eslesme.group(2)
        if grup is None:
            bulunan.append(ImportRef(taban, (taban.rsplit("\\", 1)[-1],)))
            continue
        for parca in grup.split(","):
            ad = parca.strip().split()[0] if parca.strip() else ""
            if ad:
                bulunan.append(ImportRef(f"{taban}\\{ad}", (ad.rsplit("\\", 1)[-1],)))
    bulunan.extend(ImportRef(e.group("spec")) for e in _PHP_REQUIRE.finditer(kaynak))
    return bulunan


# --------------------------------------------------------------------------- çözümleme


def _suffix_keys(parcalar: list[str], ayrac: str) -> Iterable[str]:
    return (ayrac.join(parcalar[i:]) for i in range(len(parcalar)))


def _closest(adaylar: list[str], kaynak: str) -> str:
    """Birden çok aday varsa kaynağa en yakın dizinde olanı seç (belirleyici)."""
    kaynak_parcalar = kaynak.split("/")[:-1]

    def uzaklik(aday: str) -> tuple[int, int, str]:
        ortak = 0
        for a, b in zip(aday.split("/")[:-1], kaynak_parcalar, strict=False):
            if a != b:
                break
            ortak += 1
        return (-ortak, aday.count("/"), aday)

    return min(adaylar, key=uzaklik)


@dataclass(slots=True)
class ModuleIndex:
    """Çözümleme için dosya yollarından kurulan arama tabloları."""

    paths: frozenset[str]
    _py: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    _py_kok: dict[str, str] = field(default_factory=dict)
    _php: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    _uzantisiz: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    _uzantili: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))

    @classmethod
    def build(cls, yollar: Iterable[str]) -> ModuleIndex:
        sirali = sorted(set(yollar))
        index = cls(frozenset(sirali))
        for yol in sirali:
            parcalar = yol.split("/")
            ad, _, uzanti = parcalar[-1].rpartition(".")
            if not ad:
                continue
            govdesiz = [*parcalar[:-1], ad]
            for anahtar in _suffix_keys(parcalar, "/"):
                index._uzantili[anahtar].append(yol)
            for anahtar in _suffix_keys(govdesiz, "/"):
                index._uzantisiz[anahtar].append(yol)
            if uzanti == "py":
                modul = govdesiz[:-1] if ad == "__init__" else govdesiz
                for anahtar in _suffix_keys(modul, "."):
                    if anahtar:
                        index._py[anahtar].append(yol)
                index._py_kok.setdefault(".".join(modul), yol)
                if len(modul) > 1 and modul[0] in _SOURCE_ROOTS:
                    index._py_kok.setdefault(".".join(modul[1:]), yol)
            elif uzanti == "php":
                for anahtar in _suffix_keys(govdesiz, "/"):
                    index._php[anahtar].append(yol)
        return index

    # Python ----------------------------------------------------------------

    def python_module(self, noktali: str, kaynak: str) -> str | None:
        """`a.b.c` mutlak modülünü dosyaya çöz; kütüphane adları yalnız kökten eşleşir."""
        if not noktali:
            return None
        kok = self._py_kok.get(noktali)
        if kok is not None:
            return kok
        if noktali.split(".", 1)[0] in _STDLIB:
            return None
        adaylar = self._py.get(noktali)
        return _closest(adaylar, kaynak) if adaylar else None

    def python_relative(self, kaynak: str, seviye: int, noktali: str) -> str | None:
        """`from ..x import y` için göreli modülü çöz."""
        taban = posixpath.dirname(kaynak)
        for _ in range(seviye - 1):
            if not taban:
                return None
            taban = posixpath.dirname(taban)
        hedef = posixpath.join(taban, *noktali.split(".")) if noktali else taban
        for aday in (f"{hedef}.py", f"{hedef}/__init__.py"):
            if aday in self.paths:
                return aday
        return None

    # JS/TS -----------------------------------------------------------------

    def js_module(self, kaynak: str, spec: str) -> str | None:
        """JS/TS belirtecini dosyaya çöz; paket adları (`react`) çözülmez."""
        if spec.startswith("."):
            taban = posixpath.normpath(posixpath.join(posixpath.dirname(kaynak), spec))
            if taban.startswith(".."):
                return None
            return self._js_aday(taban)
        for onek in _ALIAS_PREFIXES:
            if spec.startswith(onek):
                kalan = spec[len(onek) :]
                for deneme in (kalan, f"{kalan}/index"):
                    adaylar = [
                        y for y in self._uzantisiz.get(deneme, ()) if y.endswith(_JS_SUFFIXES)
                    ]
                    if adaylar:
                        return _closest(adaylar, kaynak)
                return None
        return None

    def _js_aday(self, taban: str) -> str | None:
        if taban in self.paths:
            return taban
        govde, uzanti = posixpath.splitext(taban)
        olasi = [f"{taban}{u}" for u in _JS_SUFFIXES]
        olasi += [f"{govde}{u}" for u in _JS_JS_TO_TS.get(uzanti, ())]
        olasi += [f"{taban}/index{u}" for u in _JS_SUFFIXES]
        return next((a for a in olasi if a in self.paths), None)

    # PHP -------------------------------------------------------------------

    def php_class(self, ad_alani: str, kaynak: str) -> str | None:
        """`A\\B\\C` sınıfını `…/B/C.php`'ye çöz (PSR-4 öneki bilinmediği için sondan eşle)."""
        parcalar = ad_alani.split("\\")
        for bas in range(len(parcalar)):
            adaylar = self._php.get("/".join(parcalar[bas:]))
            if not adaylar:
                continue
            # Tek parçalı anahtar (`User`) yalnız benzersizse güvenilir.
            if len(parcalar) - bas == 1 and len(adaylar) > 1:
                return None
            return _closest(adaylar, kaynak)
        return None

    def php_file(self, kaynak: str, spec: str) -> str | None:
        """`require 'inc/x.php'` yolunu çöz: önce kaynağa göre, sonra kökten, sonra sondan."""
        temiz = spec.lstrip("/")
        for taban in (posixpath.dirname(kaynak), ""):
            aday = posixpath.normpath(posixpath.join(taban, temiz))
            if not aday.startswith("..") and aday in self.paths:
                return aday
        adaylar = self._uzantili.get(posixpath.normpath(temiz))
        return _closest(adaylar, kaynak) if adaylar else None


# --------------------------------------------------------------------------- graf


@dataclass(frozen=True, slots=True)
class ImportGraph:
    """Test olmayan dosyalardan gelen içe aktarma sayıları."""

    fan_in: Mapping[str, int]
    named_in: Mapping[tuple[str, str], int]
    edges: int


def _targets(
    kaynak: str, uzanti: str, ref: ImportRef, index: ModuleIndex
) -> list[tuple[str, bool]]:
    """(hedef dosya, adlar bu dosyaya mı yazılır) çiftleri."""
    if uzanti == ".py":
        return _python_targets(kaynak, ref, index)
    if uzanti == ".php":
        hedef = index.php_class(ref.spec, kaynak) if ref.names else index.php_file(kaynak, ref.spec)
        return [(hedef, True)] if hedef else []
    hedef = index.js_module(kaynak, ref.spec)
    return [(hedef, True)] if hedef else []


def _python_targets(kaynak: str, ref: ImportRef, index: ModuleIndex) -> list[tuple[str, bool]]:
    if ref.level:
        ana = index.python_relative(kaynak, ref.level, ref.spec)
    else:
        ana = index.python_module(ref.spec, kaynak)
    bulunan: list[tuple[str, bool]] = [(ana, True)] if ana else []
    # `from pkg import alt_modul`: ad bir alt MODÜL de olabilir.
    for ad in ref.names:
        if ref.level:
            alt_modul = f"{ref.spec}.{ad}" if ref.spec else ad
            alt = index.python_relative(kaynak, ref.level, alt_modul)
        else:
            alt = index.python_module(f"{ref.spec}.{ad}" if ref.spec else ad, kaynak)
        if alt and alt != ana:
            bulunan.append((alt, False))
    return bulunan


def build_graph(
    imports: Mapping[str, list[ImportRef]],
    index: ModuleIndex,
    *,
    is_test: Callable[[str], bool],
) -> ImportGraph:
    """İçe aktarma bildirimlerinden `fan_in` ve `named_in` sayımlarını çıkar.

    Her (içe aktaran, hedef) çifti BİR kez sayılır; bir dosyanın kendisini içe
    aktarması ve test dosyalarından gelen kenarlar sayılmaz (testler her şeyi içe
    aktarır; sinyal olsa harita test koduyla dolardı).
    """
    fan_in: dict[str, int] = defaultdict(int)
    named_in: dict[tuple[str, str], int] = defaultdict(int)
    gorulen_kenar: set[tuple[str, str]] = set()
    gorulen_ad: set[tuple[str, str, str]] = set()
    for kaynak in sorted(imports):
        if is_test(kaynak):
            continue
        uzanti = posixpath.splitext(kaynak)[1]
        for ref in imports[kaynak]:
            for hedef, adli in _targets(kaynak, uzanti, ref, index):
                if hedef == kaynak:
                    continue
                if (kaynak, hedef) not in gorulen_kenar:
                    gorulen_kenar.add((kaynak, hedef))
                    fan_in[hedef] += 1
                if not adli:
                    continue
                for ad in ref.names:
                    if (kaynak, hedef, ad) not in gorulen_ad:
                        gorulen_ad.add((kaynak, hedef, ad))
                        named_in[(hedef, ad)] += 1
    return ImportGraph(fan_in, named_in, len(gorulen_kenar))
