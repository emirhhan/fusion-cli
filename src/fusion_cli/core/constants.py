"""Araç katmanının sayısal sınırları — tek yerde tanımlıdır.

Bu değerler koda dağıtılmaz: bir sınırı değiştirmek tek satır değiştirmektir ve
"acaba başka nerede geçiyordu?" sorusu hiç doğmaz.

Sınırların amacı bağlamı korumaktır: model bir aracın çıktısını okuyacaktır, binlerce
satırlık bir dökümü bağlama boca etmek hem pahalı hem de sinyali gürültüde boğar.
"""

from __future__ import annotations

#: Bir dosyadan okunacak en fazla bayt.
MAX_READ_BYTES = 100_000
#: Bir araç çıktısının modele verilecek en fazla karakteri.
MAX_OUTPUT_CHARS = 20_000
#: Metin/regex aramasında döndürülecek en fazla eşleşme.
MAX_SEARCH_HITS = 100
#: Bir eşleşme satırından gösterilecek en fazla karakter.
MAX_MATCH_LINE_CHARS = 160
#: Desenle bulunacak en fazla dosya.
MAX_GLOB_MATCHES = 200
#: Bir dizinde listelenecek en fazla giriş.
MAX_DIR_ENTRIES = 200
#: Aranırken atlanacak en büyük dosya boyutu (bayt).
MAX_SEARCHABLE_FILE_BYTES = 1_000_000
#: Yeni dosya önizlemesinde gösterilecek en fazla satır.
MAX_PREVIEW_LINES = 40

#: Kabuk komutu için zaman aşımı (saniye).
SHELL_TIMEOUT_S = 120.0
#: Salt-okunur git komutu için zaman aşımı (saniye).
GIT_TIMEOUT_S = 30.0
#: Web isteği için zaman aşımı (saniye). Bu bir HTTP İSTEĞİ bütçesidir (arama,
#: sayfa çekme, katalog); bir LLM turunun bütçesi DEĞİLDİR. Tarayıcı tabanlı bir
#: sohbet turu sayfa yükleme + yazma + tam streaming üretim içerir ve buraya sığmaz;
#: onun bütçesi `WebSessionConfig.timeout_s` alanından gelir.
WEB_TIMEOUT_S = 20.0
#: Tarayıcı turu için kabul edilebilir EN KISA bütçe (saniye). Yapılandırma bunun
#: altına inerse tur daha başlamadan zaman aşımına uğrar; taban buradadır.
MIN_BROWSER_TURN_S = 30.0
#: Panel model kataloğu önbellek ömrü (saniye). Katalog sık değişmez; her panel
#: açılışında sağlayıcının /models ucunu dövmemek için 5 dakika tutulur.
CATALOG_CACHE_TTL_S = 300.0
#: Web aramasından döndürülecek en fazla sonuç.
MAX_WEB_RESULTS = 8
#: `web_fetch` için elle takip edilecek en fazla yönlendirme. Her adım SSRF'e karşı
#: yeniden doğrulanır; sonsuz/uzun yönlendirme zinciri bu sınırla kesilir.
MAX_WEB_REDIRECTS = 5

#: Keşif ve arama sırasında atlanan gürültü dizinleri.
SKIP_DIRECTORIES = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".fusion",
        "dist",
        "build",
        ".next",
        ".cache",
        "target",
        ".idea",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }
)

#: `list_dir` çıktısında gizli olmasına rağmen gösterilen dosyalar.
VISIBLE_DOTFILES = frozenset({".env.example", ".gitignore", ".github"})


def truncate_notice(text: str, limit: int, *, ne: str = "çıktı") -> str:
    """Metni sınıra indir ve KIRPILDIĞINI söyle.

    Sessiz kırpma araçların en sinsi yalanıdır: model eksik bilgiyi tam sanır.
    Uzun bir test çıktısında gerçek hatayı hiç görmeden "geçti" sanabilir.
    """
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[… {ne} {limit} karakterde KIRPILDI; gerisi gösterilmedi.]"
