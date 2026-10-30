"""Depo haritası — bütçeye sığan, önem sırasına göre sembol özeti.

Aider'ın ölçümü: sembol grafiğini çıkarıp referans sayısına göre sıralamak, büyük
depoda hem ucuz kalmanın hem doğru dosyayı bulmanın ana yolu. Fusion'da yalnız
`grep` vardı ve model doğru dosyayı bulmak için tur harcıyordu.

Harita TAHMİN ETMEZ: yalnız kaynakta gerçekten yazan tanımları ve onlara yapılan
referansları sayar. Bütçe dolduğunda en çok referans alan semboller kalır — bir
fonksiyonu yirmi yerden çağırıyorsa, tek yerden çağrılan yardımcıdan daha çok
bağlam değeri taşır.

Ayrıştırma dile göre REGEX'tir, tam bir çözümleyici değil: tree-sitter bağımlılığı
paketli runtime'ı büyütür ve harita "kesin doğru" olmak zorunda değildir — yönlendirir,
karar vermez. Yanlış bir satır modeli yanlış dosyaya yollamaz, yalnız sıralamayı
gürültülendirir.

Sıralama (30 Ekim 2026, yol haritası 8. adım): yalnız "ad kaç kez geçiyor" sayımı genel
adları (`result`, `config`, `text`) ve test dosyalarını öne çıkarıyordu — bu deponun 3.000
karakterlik haritasının ~%55'i test dosyasıydı ve en çok içe aktarılan 20 dosyadan yalnız
2'si görünüyordu. Şimdi `core/repo_imports` yalın bir içe aktarma grafı kurar (Python,
JS/TS, PHP; regex); sembol puanı = 3 × (adını açıkça içe aktaran dosya) + (dosyayı içe
aktaran dosya). Test dosyaları grafa girmez ve okumada sona kalır; çıkarımı olmayan
dillerde eski sayım (tavanlı) sürer. Aynı depo → bayt-aynı çıktı: okuma sırası, kenar
çözümü ve sıralama anahtarı belirleyicidir. Soğuk çözümleme `TIME_LIMIT_S` (0,3 sn) ile
sınırlıdır; aşılırsa okunan dosyalarla kısmi harita üretilir, bunu söyler ve imza değişene
kadar aynı kalır. tree-sitter hâlâ YOK; `register_definition_extractor` / entry-point
grubu yalnız isteğe bağlı bir eklenti noktasıdır (kurulu değilse davranış aynı).

Başarım (22 Eylül 2026'da fusion-cli deposunun kendisinde ölçüldü): ilk yazımda
referans sayımı her sembol için ayrı regex derleyip BÜTÜN dosya metinlerini
tarıyordu — `O(sembol × toplam_karakter)`. 13.889 sembol × 75 milyon karakter =
**164,6 dakika**. Harita her kök agent turunda üretildiği için Fusion gerçek
boyutta hiçbir depoda çalışamıyordu. Üç şey değişti: (1) sayım tek kelime
geçişine indi, (2) gürültü dizinlerine artık HİÇ girilmiyor (eskiden yürüyüş
içeri giriyor, sonra yolu atıyordu), (3) pahalı çözümleme dosya imzasına göre
önbelleğe alındı.
"""

from __future__ import annotations

import importlib.metadata
import posixpath
import re
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import islice
from pathlib import Path

from .project_files import project_files
from .repo_imports import (
    GRAPH_SUFFIXES,
    ImportGraph,
    ImportRef,
    ModuleIndex,
    build_graph,
    extract_imports,
)

#: Dosya uzantısı → tanım deseni. Yeni dil eklemek buraya bir satır eklemektir.
#: JS/TS ailesi: function/class/interface/enum/type ve `const f = (...) =>` okları.
#: Düz `const SAYI = 5` tanım sayılmaz (gürültü). İki ad grubu var; `lastgroup` ile okunur.
_JS_ADI = r"[A-Za-z_$][\w$]*"
_JS_TANIM = re.compile(
    rf"^(?:export\s+(?:default\s+)?)?(?:declare\s+)?"
    rf"(?:(?:async\s+)?(?:function\*?|class|interface|enum|type|abstract\s+class)\s+(?P<ad>{_JS_ADI})"
    rf"|(?:const|let)\s+(?P<ok>{_JS_ADI})(?=\s*(?::[^=\n]+)?=\s*(?:async\s*)?"
    rf"(?:\([^)\n]*\)|{_JS_ADI})\s*(?::[^=\n]+)?=>))",
    re.MULTILINE,
)
_ADI = r"(?P<ad>[A-Za-z_]\w*)"

#: Dosya uzantısı → tanım deseni. Yeni dil eklemek buraya bir satır eklemektir.
_DEFINITIONS: dict[str, re.Pattern[str]] = {
    ".py": re.compile(r"^(?:async\s+)?(?:def|class)\s+(?P<ad>[A-Za-z_]\w*)", re.MULTILINE),
    ".js": _JS_TANIM,
    ".mjs": _JS_TANIM,
    ".cjs": _JS_TANIM,
    ".jsx": _JS_TANIM,
    ".ts": _JS_TANIM,
    ".tsx": _JS_TANIM,
    ".gd": re.compile(r"^func\s+(?P<ad>[A-Za-z_]\w*)", re.MULTILINE),
    ".rs": re.compile(r"^(?:pub\s+)?fn\s+(?P<ad>[A-Za-z_]\w*)", re.MULTILINE),
    ".go": re.compile(r"^func\s+(?:\([^)]*\)\s*)?(?P<ad>[A-Za-z_]\w*)", re.MULTILINE),
    ".php": re.compile(
        rf"^[ \t]*(?:(?:abstract|final)\s+)?(?:function|class|interface|trait)\s+&?{_ADI}",
        re.MULTILINE,
    ),
    ".java": re.compile(
        rf"^[ \t]*(?:(?:public|protected|private|static|final|abstract)\s+)*"
        rf"(?:class|interface|enum|record)\s+{_ADI}",
        re.MULTILINE,
    ),
    ".cs": re.compile(
        rf"^[ \t]*(?:(?:public|internal|private|protected|static|sealed|abstract|partial)\s+)*"
        rf"(?:class|interface|struct|enum|record)\s+{_ADI}",
        re.MULTILINE,
    ),
    ".kt": re.compile(
        rf"^[ \t]*(?:(?:public|private|internal|data|sealed|open|abstract|suspend)\s+)*"
        rf"(?:fun|class|object|interface)\s+{_ADI}",
        re.MULTILINE,
    ),
    ".swift": re.compile(
        rf"^[ \t]*(?:(?:public|private|internal|final|open)\s+)*"
        rf"(?:func|class|struct|enum|protocol)\s+{_ADI}",
        re.MULTILINE,
    ),
    ".rb": re.compile(rf"^[ \t]*(?:def|class|module)\s+(?:self\.)?{_ADI}", re.MULTILINE),
}

#: Varsayılan harita bütçesi (karakter). ~1k token: Aider'ın repo map bütçesiyle aynı
#: ölçek. Kullanıcı `runtime.repo_map_chars` ile değiştirir (bkz. `engines/agent/repo_context`).
DEFAULT_BUDGET_CHARS = 3_000

#: Haritada tek dosyadan görünecek en fazla tanım: bir dev modül haritanın tamamını yemesin.
_MAX_PER_FILE = 12
#: Dosya başına puanlanmak üzere taranan en fazla tanım. Tanımlar önce puanlanır, SONRA
#: `_MAX_PER_FILE` ile kesilir: 100 tanımlı bir modülde içe aktarılan adlar ilk on ikide
#: olmak zorunda değildir.
_MAX_DEFS_SCAN = 200

#: Aynı ADIN haritada en fazla kaç kez görüneceği.
#
# Sıralama sembolün puanına bakar, o yüzden en sık kullanılan isim bütün bütçeyi
# yiyebilir: ölçüldü, bu deponun haritasının ilk dokuz satırı dokuz ayrı test
# dosyasındaki `config` fixture'ıydı. Aynı gerekçe `_MAX_PER_FILE` için de geçerli —
# tek bir şey haritayı ele geçirmesin.
_MAX_PER_SYMBOL = 2

#: Çözümlemeye alınacak en fazla kaynak dosya ve en fazla toplam karakter.
#
# Ölçüm (fusion-cli deposu, 22 Eylül): 4.789 dosya / 75.069.360 karakter, yeni
# uygulamayla 9,2 sn. Tavanlar bu ölçümün ~2 katına konuldu — bu depo rahatça
# altında kalsın, ama patolojik bir ağaç (tek dizine boşaltılmış bir veri kümesi)
# turu askıda bırakmasın. Tavan aşılırsa harita ÜRETİLİR ve kısmi olduğunu söyler.
_MAX_FILES = 10_000
_MAX_TOTAL_CHARS = 150_000_000
#: Bundan büyük dosya (üretilmiş paket, minify, veri dökümü) okunmaz: harita için
#: değersiz ve okuma maliyetinin asıl kalemi.
_MAX_FILE_BYTES = 300_000

#: Soğuk çözümleme için zaman sınırı (saniye). Sınır aşılırsa okunan dosyalarla harita
#: üretilir ve kısmi olduğunu söyler. Okuma sırası belirleyicidir (önce kaynak, sonra
#: test; sığ yol önce), böylece kesilen harita yine en önemli dizinleri içerir. Önbellek
#: imzayla anahtarlandığından aynı ağaçta aynı (kısmi) metin turdan tura döner.
TIME_LIMIT_S = 0.3

#: Sembol puanı = `_NAMED_WEIGHT` × (adını açıkça içe aktaran dosya sayısı) + (dosyayı
#: içe aktaran dosya sayısı). Ad bir ilişkiyi tek başına, dosya bir hub'ı gösterir;
#: adlı içe aktarma daha spesifik bir sinyal olduğundan 3 kat tartılır. TAHMİN: canlı
#: ölçümle güncellenecek.
_NAMED_WEIGHT = 3
#: İçe aktarma çıkarımı olmayan dillerde (Go, Rust…) puan eski sayımdır (adın depoda
#: kaç kez geçtiği); `fn new` gibi genel adlar graflı dillerin puanını ezmesin diye
#: bu değerle sınırlanır.
_FALLBACK_CAP = 12

#: Zamanı okuyan işlev; testte sabitlenir.
_simdi = time.perf_counter

#: Test/fixture yolları: okuma sırasında sona atılır, içe aktarma sayımına girmez.
_TEST_DIRS = frozenset(
    {"tests", "test", "__tests__", "__mocks__", "e2e", "spec", "specs", "fixtures", "testdata"}
)

#: Referans sayımında kullanılan tanımlayıcı deseni (graf dışı diller için).
#
# Eski `\bAD\b` regex'iyle DAVRANIŞÇA aynıdır: tanım adları her zaman
# `[A-Za-z_]\w*` biçiminde olduğu için `oran2`, `_oran` gibi komşular iki yolda da
# eşleşmez. Fark yalnız maliyettedir — sembol başına değil, dosya başına bir geçiş.
_IDENTIFIER = re.compile(r"[A-Za-z_]\w*")

# --------------------------------------------------------------------------- eklenti noktası

#: Tanım çıkarıcı: kaynak metni alır, tanım adlarını döndürür; `None` = "bu dosyayı
#: ben çözemedim, regex'e düş". tree-sitter gibi gerçek bir çözümleyici BURAYA takılır;
#: paketli runtime onu içermez ve kurulu değilse davranış harfiyen aynıdır.
DefinitionExtractor = Callable[[str], Sequence[str] | None]

#: Üçüncü taraf paketlerin çıkarıcı bildirdiği entry-point grubu. Ad = uzantı (`.py`),
#: değer = `DefinitionExtractor` çağrılabilir. Yalnız KURULU paketlerden okunur (proje
#: dizinindeki kod buradan yüklenmez).
ENTRY_POINT_GROUP = "fusion_cli.repo_map_extractors"

_EXTRACTORS: dict[str, DefinitionExtractor] = {}
_plugins_loaded = False


def register_definition_extractor(suffix: str, extractor: DefinitionExtractor) -> None:
    """Bir uzantı için regex yerine geçecek tanım çıkarıcıyı kaydet.

    Çıkarıcı `None` döndürür ya da hata fırlatırsa o dosya için regex kullanılır.
    Kayıt önbelleği temizler: çıkarıcı değişince eski harita geçersizdir.
    """
    _EXTRACTORS[suffix] = extractor
    _CACHE.clear()


def _load_plugins() -> None:
    """Kurulu paketlerin entry-point'lerini bir kez yükle; hiç yoksa hiçbir şey olmaz."""
    global _plugins_loaded  # süreç başına bir kez yükleme bayrağı
    if _plugins_loaded:
        return
    _plugins_loaded = True
    try:
        noktalar = sorted(importlib.metadata.entry_points(group=ENTRY_POINT_GROUP), key=str)
    except Exception:  # eklenti keşfi haritayı asla düşüremez
        return
    for nokta in noktalar:
        try:
            cikarici = nokta.load()
        except Exception:  # bozuk eklenti atlanır, regex yolu kalır
            continue
        if callable(cikarici):
            _EXTRACTORS.setdefault(nokta.name, cikarici)


def _definitions(suffix: str, kaynak: str) -> list[str]:
    """Dosyadaki tanım adları: önce eklenti, yoksa/çözemezse regex."""
    cikarici = _EXTRACTORS.get(suffix)
    if cikarici is not None:
        try:
            adlar = cikarici(kaynak)
        except Exception:  # eklenti hatası regex'e düşer
            adlar = None
        if adlar is not None:
            return [ad for ad in adlar if isinstance(ad, str) and ad][:_MAX_DEFS_SCAN]
    desen = _DEFINITIONS.get(suffix)
    if desen is None:
        return []
    return [
        eslesme.group(eslesme.lastgroup or "ad")
        for eslesme in islice(desen.finditer(kaynak), _MAX_DEFS_SCAN)
    ]


# --------------------------------------------------------------------------- sonuç tipleri


@dataclass(frozen=True, slots=True)
class RepoMapStats:
    """Haritanın ölçüm izi (olay/denetim kaydına yazılır)."""

    #: Üretilen metnin karakteri ve istenen bütçe.
    chars: int
    budget_chars: int
    #: Uzantısı haritaya uygun dosya sayısı ve gerçekten okunanlar.
    candidates: int
    files: int
    #: Bulunan toplam tanım, haritada gösterilen tanım, çözülen içe aktarma kenarı.
    symbols: int
    shown: int
    edges: int
    elapsed_ms: int
    #: Harita kısmi mi (dosya/karakter tavanı ya da zaman sınırı) ve neden zaman.
    partial: bool
    time_limited: bool
    #: Çözümleme önbellekten mi geldi?
    cached: bool


@dataclass(frozen=True, slots=True)
class RepoMapResult:
    text: str
    stats: RepoMapStats


@dataclass(frozen=True, slots=True)
class _Entry:
    path: Path
    rel: str
    size: int


@dataclass(frozen=True, slots=True)
class _Analysis:
    #: Puan sırasına dizilmiş (dosya, ad) çiftleri.
    ranked: tuple[tuple[str, str], ...]
    capped: bool
    time_limited: bool
    read: int
    candidates: int
    edges: int


#: (kök) → (imza, çözümleme). Pahalı olan okuma+çözümlemedir; yürüyüş ucuzdur, o
# yüzden imza her çağrıda yeniden hesaplanır ve önbellek doğru kalır.
_CACHE: dict[str, tuple[tuple[int, int, int], _Analysis]] = {}
#: Önbellekte tutulan en fazla kök. Fusion birden çok projeyi aynı anda açabiliyor.
_CACHE_LIMIT = 4


def is_test_path(rel: str) -> bool:
    """Yol bir test/fixture dosyası mı? (haritada geriye atılır, grafa girmez)."""
    parcalar = rel.split("/")
    ad = parcalar[-1]
    kucuk = ad.lower()
    return (
        any(parca in _TEST_DIRS for parca in parcalar[:-1])
        or kucuk.startswith("test_")
        or kucuk == "conftest.py"
        or ".test." in kucuk
        or ".spec." in kucuk
        or kucuk.endswith(("_test.py", "_test.go", "_test.rs"))
        or ad.endswith("Test.php")
    )


# --------------------------------------------------------------------------- üretim


def build_repo_map(
    root: Path,
    *,
    budget_chars: int = DEFAULT_BUDGET_CHARS,
    time_limit_s: float = TIME_LIMIT_S,
) -> str:
    """Bütçeye sığan depo haritasını üret; proje boşsa boş metin."""
    return build_repo_map_report(root, budget_chars=budget_chars, time_limit_s=time_limit_s).text


def build_repo_map_report(
    root: Path,
    *,
    budget_chars: int = DEFAULT_BUDGET_CHARS,
    time_limit_s: float = TIME_LIMIT_S,
) -> RepoMapResult:
    """Haritayı ve ölçüm izini birlikte üret (aynı depo → bayt-aynı metin)."""
    _load_plugins()
    basla = _simdi()
    yollar, kisitli = _source_files(root)
    if not yollar or budget_chars <= 0:
        return RepoMapResult("", _stats(0, budget_chars, None, 0, basla, cached=False))

    girdiler, imza = _entries(root, yollar)
    anahtar = str(root.resolve())
    onbellek = _CACHE.get(anahtar)
    cached = onbellek is not None and onbellek[0] == imza
    if onbellek is not None and cached:
        analiz = onbellek[1]
    else:
        analiz = _analyze(girdiler, kisitli, time_limit_s)
        if analiz.ranked:
            if len(_CACHE) >= _CACHE_LIMIT:
                _CACHE.pop(next(iter(_CACHE)))
            _CACHE[anahtar] = (imza, analiz)
    if not analiz.ranked:
        return RepoMapResult("", _stats(0, budget_chars, analiz, 0, basla, cached=cached))
    metin, gosterilen = _render(analiz, budget_chars)
    return RepoMapResult(metin, _stats(len(metin), budget_chars, analiz, gosterilen, basla, cached))


def _stats(
    chars: int,
    budget: int,
    analiz: _Analysis | None,
    shown: int,
    basla: float,
    cached: bool,
) -> RepoMapStats:
    ms = round((_simdi() - basla) * 1000)
    if analiz is None:
        return RepoMapStats(chars, budget, 0, 0, 0, shown, 0, ms, False, False, cached)
    return RepoMapStats(
        chars=chars,
        budget_chars=budget,
        candidates=analiz.candidates,
        files=analiz.read,
        symbols=len(analiz.ranked),
        shown=shown,
        edges=analiz.edges,
        elapsed_ms=ms,
        partial=analiz.capped or analiz.time_limited,
        time_limited=analiz.time_limited,
        cached=cached,
    )


def _source_files(root: Path) -> tuple[list[Path], bool]:
    """Haritaya girecek kaynak dosyalar ve dosya tavanının aşılıp aşılmadığı.

    Dosya listesini `core.project_files` üretir (git biliyorsa ondan, yoksa
    budamalı yürüyüşten); burada yalnız uzantı süzgeci uygulanır. Aynı mantık
    `@` ile dosya anmada da kullanılıyor, o yüzden tek yerde durur.
    """
    tumu, kisitli = project_files(root, limit=_MAX_FILES * 8)
    yollar = [yol for yol in tumu if yol.suffix in _DEFINITIONS or yol.suffix in _EXTRACTORS]
    if len(yollar) > _MAX_FILES:
        return yollar[:_MAX_FILES], True
    return yollar, kisitli


def _entries(root: Path, yollar: list[Path]) -> tuple[list[_Entry], tuple[int, int, int]]:
    """Dosyaları bir kez `stat` et: okuma listesi ve ucuz parmak izi (sayı, boyut, zaman).

    Üçü birden değişmeden kalan bir ağaçta harita da değişmez. `stat` yürüyüşün
    yanında ucuzdur; asıl maliyet kaynağı okuyup çözmektir ve önbellek tam onu atlar.
    """
    girdiler: list[_Entry] = []
    boyut = 0
    zaman = 0
    for yol in yollar:
        try:
            bilgi = yol.stat()
        except OSError:
            continue
        boyut += bilgi.st_size
        zaman += bilgi.st_mtime_ns
        girdiler.append(_Entry(yol, yol.relative_to(root).as_posix(), bilgi.st_size))
    return girdiler, (len(girdiler), boyut, zaman)


def _read_order(girdi: _Entry) -> tuple[bool, int, str]:
    """Okuma önceliği: önce kaynak, sonra test; sığ yol önce; sonra yol sırası."""
    return (is_test_path(girdi.rel), girdi.rel.count("/"), girdi.rel)


def _analyze(girdiler: list[_Entry], kisitli: bool, time_limit_s: float) -> _Analysis:
    """Dosyaları öncelik sırasıyla (zaman sınırına kadar) okuyup tanım+içe aktarma çıkar,
    grafı kur ve sembolleri puanla."""
    basla = _simdi()
    tanimlar: dict[str, list[str]] = {}
    ice_aktarmalar: dict[str, list[ImportRef]] = {}
    serbest_sayim: Counter[str] = Counter()
    toplam_karakter = 0
    okunan = 0
    asildi = False
    zaman_asildi = False
    for girdi in sorted(girdiler, key=_read_order):
        if _simdi() - basla > time_limit_s:
            zaman_asildi = True
            break
        if girdi.size > _MAX_FILE_BYTES:
            continue
        try:
            kaynak = girdi.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        toplam_karakter += len(kaynak)
        if toplam_karakter > _MAX_TOTAL_CHARS:
            asildi = True
            break
        okunan += 1
        uzanti = girdi.path.suffix
        adlar = _definitions(uzanti, kaynak)
        if adlar:
            tanimlar[girdi.rel] = adlar
        if uzanti in GRAPH_SUFFIXES:
            ice_aktarmalar[girdi.rel] = extract_imports(uzanti, kaynak)
        elif adlar:
            serbest_sayim.update(_IDENTIFIER.findall(kaynak))
    if not tanimlar:
        return _Analysis((), kisitli or asildi, zaman_asildi, okunan, len(girdiler), 0)

    indeks = ModuleIndex.build(g.rel for g in girdiler if g.path.suffix in GRAPH_SUFFIXES)
    graf = build_graph(ice_aktarmalar, indeks, is_test=is_test_path)
    sirali = _rank(tanimlar, graf, serbest_sayim)
    return _Analysis(sirali, kisitli or asildi, zaman_asildi, okunan, len(girdiler), graf.edges)


def _rank(
    tanimlar: dict[str, list[str]], graf: ImportGraph, serbest_sayim: Counter[str]
) -> tuple[tuple[str, str], ...]:
    """Sembolleri puana göre diz: (-puan, -dosya içe aktarılma, dosya, ad) — tam sıra."""
    anahtarlar: list[tuple[int, int, str, str]] = []
    for dosya, adlar in tanimlar.items():
        dosya_gelen = graf.fan_in.get(dosya, 0)
        graflı = posixpath.splitext(dosya)[1] in GRAPH_SUFFIXES
        for ad in adlar:
            if graflı:
                puan = _NAMED_WEIGHT * graf.named_in.get((dosya, ad), 0) + dosya_gelen
            else:
                puan = min(serbest_sayim.get(ad, 0), _FALLBACK_CAP)
            anahtarlar.append((-puan, -dosya_gelen, dosya, ad))
    anahtarlar.sort()
    return tuple((dosya, ad) for _, _, dosya, ad in anahtarlar)


def _render(analiz: _Analysis, budget: int) -> tuple[str, int]:
    """Bütçeyi AŞMADAN en önemli tanımlardan liste üret; (metin, gösterilen sayısı)."""
    satirlar: list[str] = []
    uzunluk = 0
    if analiz.capped or analiz.time_limited:
        # Kısmi olduğunu SÖYLEMEK, sessizce eksik harita vermekten iyidir: model
        # "bu listede yoksa dosya yoktur" diye düşünmesin.
        neden = (
            "depo tavanı ve zaman sınırı"
            if analiz.capped and analiz.time_limited
            else "zaman sınırı"
            if analiz.time_limited
            else "depo tavanı"
        )
        uyari = f"({neden} aşıldı: harita kısmi)"
        if len(uyari) + 1 <= budget:
            satirlar.append(uyari)
            uzunluk = len(uyari) + 1
    gorulen: Counter[str] = Counter()
    dosya_sayisi: Counter[str] = Counter()
    gosterilen = 0
    for dosya, ad in analiz.ranked:
        if gorulen[ad] >= _MAX_PER_SYMBOL or dosya_sayisi[dosya] >= _MAX_PER_FILE:
            continue
        satir = f"{dosya}: {ad}"
        if uzunluk + len(satir) + 1 > budget:
            break
        satirlar.append(satir)
        uzunluk += len(satir) + 1
        gorulen[ad] += 1
        dosya_sayisi[dosya] += 1
        gosterilen += 1
    return "\n".join(satirlar), gosterilen
