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
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

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

#: Taranmayan dizinler: üretilmiş çıktı ve bağımlılık ağaçları haritayı boğar.
_SKIP = frozenset(
    {
        ".git",
        ".venv",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        "dist",
        "build",
        "target",
    }
)
#: Tek bir dosyadan alınacak en fazla tanım: bir dev modül haritanın tamamını yemesin.
_MAX_PER_FILE = 12


def build_repo_map(root: Path, *, budget_chars: int = 2_000) -> str:
    """Bütçeye sığan depo haritasını üret; proje boşsa boş metin."""
    tanimlar: list[tuple[str, str]] = []
    metinler: dict[Path, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in _DEFINITIONS:
            continue
        if any(part in _SKIP for part in path.relative_to(root).parts):
            continue
        try:
            kaynak = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        metinler[path] = kaynak
        goreli = str(path.relative_to(root))
        for eslesme in list(_DEFINITIONS[path.suffix].finditer(kaynak))[:_MAX_PER_FILE]:
            tanimlar.append((goreli, eslesme.group("ad")))
    if not tanimlar:
        return ""

    referanslar = _reference_counts(metinler, [ad for _, ad in tanimlar])
    sirali = sorted(tanimlar, key=lambda item: (-referanslar[item[1]], item[0], item[1]))
    return _render(sirali, budget_chars)


def _reference_counts(metinler: dict[Path, str], adlar: list[str]) -> Counter[str]:
    """Her sembolün bütün dosyalarda kaç kez geçtiğini say."""
    sayac: Counter[str] = Counter()
    for ad in set(adlar):
        desen = re.compile(rf"\b{re.escape(ad)}\b")
        sayac[ad] = sum(len(desen.findall(kaynak)) for kaynak in metinler.values())
    return sayac


def _render(sirali: list[tuple[str, str]], budget: int) -> str:
    """Bütçeyi AŞMADAN en önemli tanımlardan liste üret."""
    satirlar: list[str] = []
    uzunluk = 0
    for dosya, ad in sirali:
        satir = f"{dosya}: {ad}"
        if uzunluk + len(satir) + 1 > budget:
            break
        satirlar.append(satir)
        uzunluk += len(satir) + 1
    return "\n".join(satirlar)
