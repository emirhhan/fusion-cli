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

import re
from collections import Counter
from pathlib import Path

from .project_files import project_files

#: Dosya uzantısı → tanım deseni. Yeni dil eklemek buraya bir satır eklemektir.
_DEFINITIONS: dict[str, re.Pattern[str]] = {
    ".py": re.compile(r"^(?:async\s+)?(?:def|class)\s+(?P<ad>[A-Za-z_]\w*)", re.MULTILINE),
    ".js": re.compile(r"^(?:export\s+)?(?:async\s+)?function\s+(?P<ad>[A-Za-z_]\w*)", re.MULTILINE),
    ".ts": re.compile(
        r"^(?:export\s+)?(?:async\s+)?(?:function|class)\s+(?P<ad>[A-Za-z_]\w*)", re.MULTILINE
    ),
    ".gd": re.compile(r"^func\s+(?P<ad>[A-Za-z_]\w*)", re.MULTILINE),
    ".rs": re.compile(r"^(?:pub\s+)?fn\s+(?P<ad>[A-Za-z_]\w*)", re.MULTILINE),
    ".go": re.compile(r"^func\s+(?:\([^)]*\)\s*)?(?P<ad>[A-Za-z_]\w*)", re.MULTILINE),
}

#: Tek bir dosyadan alınacak en fazla tanım: bir dev modül haritanın tamamını yemesin.
_MAX_PER_FILE = 12

#: Aynı ADIN haritada en fazla kaç kez görüneceği.
#
# Sıralama sembolün referans sayısına bakar, o yüzden en sık kullanılan isim
# bütün bütçeyi yiyordu: ölçüldü, bu deponun haritasının ilk dokuz satırı
# dokuz ayrı test dosyasındaki `config` fixture'ıydı. Aynı gerekçe
# `_MAX_PER_FILE` için de geçerli — tek bir şey haritayı ele geçirmesin.
_MAX_PER_SYMBOL = 2

#: Çözümlemeye alınacak en fazla kaynak dosya ve en fazla toplam karakter.
#
# Ölçüm (fusion-cli deposu, 22 Eylül): 4.789 dosya / 75.069.360 karakter, yeni
# uygulamayla 9,2 sn. Tavanlar bu ölçümün ~2 katına konuldu — bu depo rahatça
# altında kalsın, ama patolojik bir ağaç (tek dizine boşaltılmış bir veri kümesi)
# turu askıda bırakmasın. Tavan aşılırsa harita ÜRETİLİR ve kısmi olduğunu söyler.
_MAX_FILES = 10_000
_MAX_TOTAL_CHARS = 150_000_000


#: Referans sayımında kullanılan tanımlayıcı deseni.
#
# Eski `\bAD\b` regex'iyle DAVRANIŞÇA aynıdır: tanım adları her zaman
# `[A-Za-z_]\w*` biçiminde olduğu için `oran2`, `_oran` gibi komşular iki yolda da
# eşleşmez. Fark yalnız maliyettedir — sembol başına değil, dosya başına bir geçiş.
_IDENTIFIER = re.compile(r"[A-Za-z_]\w*")

#: (kök, imza) → sıralanmış tanım listesi. Pahalı olan okuma+sayımdır; yürüyüş
# ucuzdur, o yüzden imza her çağrıda yeniden hesaplanır ve önbellek doğru kalır.
_CACHE: dict[str, tuple[tuple[int, int, int], list[tuple[str, str]], bool]] = {}
#: Önbellekte tutulan en fazla kök. Fusion birden çok projeyi aynı anda açabiliyor.
_CACHE_LIMIT = 4


def build_repo_map(root: Path, *, budget_chars: int = 2_000) -> str:
    """Bütçeye sığan depo haritasını üret; proje boşsa boş metin."""
    yollar, kisitli = _source_files(root)
    if not yollar:
        return ""

    anahtar = str(root.resolve())
    imza = _signature(yollar)
    onbellek = _CACHE.get(anahtar)
    if onbellek is not None and onbellek[0] == imza:
        return _render(onbellek[1], budget_chars, onbellek[2])

    sirali, asildi = _analyze(root, yollar)
    if not sirali:
        return ""
    kisitli = kisitli or asildi
    if len(_CACHE) >= _CACHE_LIMIT:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[anahtar] = (imza, sirali, kisitli)
    return _render(sirali, budget_chars, kisitli)


def _source_files(root: Path) -> tuple[list[Path], bool]:
    """Haritaya girecek kaynak dosyalar ve dosya tavanının aşılıp aşılmadığı.

    Dosya listesini `core.project_files` üretir (git biliyorsa ondan, yoksa
    budamalı yürüyüşten); burada yalnız uzantı süzgeci uygulanır. Aynı mantık
    `@` ile dosya anmada da kullanılıyor, o yüzden tek yerde durur.
    """
    tumu, kisitli = project_files(root, limit=_MAX_FILES * 8)
    yollar = [yol for yol in tumu if yol.suffix in _DEFINITIONS]
    if len(yollar) > _MAX_FILES:
        return yollar[:_MAX_FILES], True
    return yollar, kisitli


def _signature(yollar: list[Path]) -> tuple[int, int, int]:
    """Dosya kümesinin ucuz parmak izi: sayı, toplam boyut, toplam değişim zamanı.

    Üçü birden değişmeden kalan bir ağaçta harita da değişmez. `stat` yürüyüşün
    yanında ucuzdur; asıl maliyet 75 MB kaynağı okuyup saymaktır ve önbellek tam
    onu atlar.
    """
    sayi = 0
    boyut = 0
    zaman = 0
    for yol in yollar:
        try:
            bilgi = yol.stat()
        except OSError:
            continue
        sayi += 1
        boyut += bilgi.st_size
        zaman += bilgi.st_mtime_ns
    return sayi, boyut, zaman


def _analyze(root: Path, yollar: list[Path]) -> tuple[list[tuple[str, str]], bool]:
    """Dosyaları okuyup tanımları çıkar ve referansa göre sırala."""
    tanimlar: list[tuple[str, str]] = []
    metinler: list[str] = []
    toplam_karakter = 0
    asildi = False
    for path in yollar:
        try:
            kaynak = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        toplam_karakter += len(kaynak)
        if toplam_karakter > _MAX_TOTAL_CHARS:
            asildi = True
            break
        metinler.append(kaynak)
        goreli = str(path.relative_to(root))
        for eslesme in list(_DEFINITIONS[path.suffix].finditer(kaynak))[:_MAX_PER_FILE]:
            tanimlar.append((goreli, eslesme.group("ad")))
    if not tanimlar:
        return [], asildi

    referanslar = _reference_counts(metinler, [ad for _, ad in tanimlar])
    sirali = sorted(tanimlar, key=lambda item: (-referanslar[item[1]], item[0], item[1]))
    return sirali, asildi


def _reference_counts(metinler: list[str], adlar: list[str]) -> Counter[str]:
    """Her sembolün bütün dosyalarda kaç kez geçtiğini say.

    Her dosya BİR KEZ kelimelere ayrılır. Eski uygulama sembol başına bir regex
    derleyip bütün metinleri baştan tarıyordu; bu depoda 164,6 dakika ediyordu.
    """
    toplam: Counter[str] = Counter()
    for kaynak in metinler:
        toplam.update(_IDENTIFIER.findall(kaynak))
    return Counter({ad: toplam.get(ad, 0) for ad in set(adlar)})


def _render(sirali: list[tuple[str, str]], budget: int, kisitli: bool = False) -> str:
    """Bütçeyi AŞMADAN en önemli tanımlardan liste üret."""
    satirlar: list[str] = []
    uzunluk = 0
    if kisitli:
        # Kısmi olduğunu SÖYLEMEK, sessizce eksik harita vermekten iyidir: model
        # "bu listede yoksa dosya yoktur" diye düşünmesin.
        uyari = "(depo tavanı aşıldı: harita kısmi)"
        if len(uyari) + 1 <= budget:
            satirlar.append(uyari)
            uzunluk = len(uyari) + 1
    gorulen: Counter[str] = Counter()
    for dosya, ad in sirali:
        if gorulen[ad] >= _MAX_PER_SYMBOL:
            continue
        satir = f"{dosya}: {ad}"
        if uzunluk + len(satir) + 1 > budget:
            break
        satirlar.append(satir)
        uzunluk += len(satir) + 1
        gorulen[ad] += 1
    return "\n".join(satirlar)
