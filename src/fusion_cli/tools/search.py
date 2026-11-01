"""Keşif araçları: metin/regex arama ve dosya deseni.

İkisi de gürültü dizinlerini atlar ve üst sınırla çalışır: modelin bağlamına
binlerce satır boca etmek sinyali gürültüde boğar.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from ..core.constants import (
    MAX_GLOB_MATCHES,
    MAX_SEARCH_HITS,
    MAX_SEARCHABLE_FILE_BYTES,
    SKIP_DIRECTORIES,
)
from ..core.localization import MAX_LOCALIZATION_CANDIDATES, localization_symbol
from ..core.redaction import redact
from ..core.source_read import read_scoped_source
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import optional_str, require_str
from .files import display_path, resolve_path

SEARCH_DEADLINE_S = 8.0
MAX_SEARCH_CANDIDATES = 50_000
MAX_SEARCH_SCAN_BYTES = 256 * 1024
MAX_SEARCH_LINE_BYTES = 16 * 1024
MAX_REGEX_PATTERN_CHARS = 500
#: Bu sayıyı aşan eşleşmede satır satır gösterim yerine dosya özeti verilir.
#
# SWE-agent'ın ACI ölçümü: her eşleşmeyi tek tek göstermek modeli şaşırtıyor;
# dosya başına kısa liste daha iyi sonuç veriyor. 20 satırlık bir liste hâlâ
# okunabilir, ötesi turu doldurur ve seçim yapmayı zorlaştırır.
MAX_DETAILED_HITS = 20

_UNSAFE_REGEX = re.compile(r"\([^()\n]{0,200}\)(?:[+*]|\{\d)")
_SECRET_FILE_NAMES = frozenset(
    {
        ".npmrc",
        ".netrc",
        ".git-credentials",
        ".pypirc",
        "firebase.json",
        "config.json",
        "config.yaml",
        "config.yml",
        "config.toml",
        "service-account.json",
        "id_rsa",
        "id_ed25519",
        "id_ecdsa",
    }
)
_SECRET_FILE_STEM_RE = re.compile(
    r"(?:^|[._-])(credential|credentials|auth|token|tokens|secret|secrets|private)"
    r"(?:$|[._-])",
    re.IGNORECASE,
)
#: Kaynak kod/doküman uzantıları: `auth.py`, `token.ts`, `use-auth.ts`, `settings.py`
#: gizli DEĞİL kaynaktır. Ölçüldü (29 Ekim): ad kalıbı bunları da atlıyor, `glob`
#: da aynı süzgeçle boş dönüyor, model "dosya yok" sanıp yeniden yazıyordu.
_SOURCE_EXTENSIONS = frozenset(
    {
        ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".php", ".go", ".rs",
        ".java", ".kt", ".swift", ".rb", ".cs", ".c", ".h", ".cpp", ".hpp", ".vue", ".svelte",
        ".md", ".mdx", ".css", ".scss", ".html", ".sh", ".sql", ".gd", ".lua", ".dart",
    }
)  # fmt: skip
_SECRET_FILE_EXTENSIONS = frozenset({".pem", ".key", ".p12", ".pfx", ".der", ".crt", ".cer"})
#: Kimlik deposu klasörleri: aranan kökün atası, kendisi ya da altında olsa da KAPALIDIR.
_CREDENTIAL_STORE_DIRECTORIES = frozenset({".aws", ".azure", ".gnupg", ".ssh"})
#: Kökün KENDİSİ bunlardan biriyse (örn. `search_code path=~/.config`) kapalıdır; ama proje
#: yolunun atası olmaları sorun değildir (`~/.config/x/proje`, `~/claude/proje`).
_PROFILE_DIRECTORIES = frozenset({".claude", ".config"})
_SECRET_DIRECTORY_NAMES = frozenset(
    {
        *_CREDENTIAL_STORE_DIRECTORIES,
        *_PROFILE_DIRECTORIES,
        "claude",
        "chrome",
        "application support",
        "cache",
        "caches",
        "vendor",
    }
)
_SKIP_DIRECTORY_NAMES = frozenset(
    name.casefold() for name in (*SKIP_DIRECTORIES, *_SECRET_DIRECTORY_NAMES)
)


@dataclass
class _SearchScan:
    context: ToolContext
    started: float
    candidates: int = 0
    stopped: str | None = None
    truncated_files: int = 0
    oversized_lines: int = 0
    skipped_secret_files: int = 0
    localization_candidates: list[dict[str, str]] = field(default_factory=list)

    def should_stop(self) -> bool:
        if self.context.cancelled.is_set():
            self.stopped = "kullanıcı tarafından iptal edildi"
        elif time.monotonic() - self.started >= SEARCH_DEADLINE_S:
            self.stopped = f"{SEARCH_DEADLINE_S:g}s süre sınırına ulaştı"
        elif self.candidates >= MAX_SEARCH_CANDIDATES:
            self.stopped = f"{MAX_SEARCH_CANDIDATES} dosyalık aday sınırına ulaştı"
        return self.stopped is not None


@dataclass(frozen=True, slots=True)
class SearchSource:
    """Çağıranın güvenli okuduğu tek kaynak; model argümanlarından üretilemez."""

    path: Path
    text: str


def _empty_note(message: str, root: Path) -> str:
    """Boş sonuç: NEREDE arandığını ve sonraki adımı söyle.

    OpenHands çalışma dizinini arama aracına yazar ("desenler bu dizine göredir").
    Ölçüldü (29 Eylül): Fusion yalnız "(eşleşen dosya yok)" diyordu; model masaüstünü
    taradığını bilmeden aynı aramayı hafifçe değiştirip tekrarladı.
    """
    return (
        f"({message}) Aranan klasör: {root}. Aradığın şey başka bir klasördeyse "
        "'path' alanına o klasörü yaz; klasör adıyla aramak için desene yalnız adı "
        "yaz (ör. 'mcp'). Aynı aramayı tekrarlamak sonucu değiştirmez."
    )


def _bounded_result(lines: list[str], scan: _SearchScan, empty: str) -> ToolResult:
    if scan.stopped is None:
        output = "\n".join(lines) if lines else empty
        if scan.skipped_secret_files:
            output += (
                f"\n\n{scan.skipped_secret_files} dosya kimlik/yapılandırma adı taşıdığı için "
                "içeriği aranmadı (ortam değişkeni, anahtar, sır ve ayar dosyaları). Biri "
                "gerekiyorsa yolunu bilerek read_file ile aç."
            )
        if scan.truncated_files or scan.oversized_lines:
            limits = []
            if scan.truncated_files:
                limits.append(f"{scan.truncated_files} dosyanın yalnız başlangıcı tarandı")
            if scan.oversized_lines:
                limits.append(f"{scan.oversized_lines} uzun satır kısaltıldı")
            output += (
                f"\n\nArama sınırları: {'; '.join(limits)}. "
                "Bu dosyaların tamamı gerekirse proje kökünde 'rg' ile ayrıca aranmalı."
            )
        return ToolResult(
            output, structured={"localization_candidates": tuple(scan.localization_candidates)}
        )
    partial = "\n".join(lines) if lines else "(bu sınır içinde eşleşme bulunmadı)"
    return ToolResult.failure(
        f"{partial}\n\nArama {scan.stopped}; {scan.candidates} dosya adayı incelendi. "
        "Bu sonuç kısmidir ve tekrar denenebilir: aynı geniş aramayı yinelemek yerine "
        "'path' alanını proje içindeki ilgili klasör veya dosyayla daraltın.",
        structured={"localization_candidates": tuple(scan.localization_candidates)},
    )


def search_code(
    args: ToolArgs, context: ToolContext, *, source: SearchSource | None = None
) -> ToolResult:
    pattern = require_str(args, "pattern")
    root = resolve_path(context, optional_str(args, "path", ".")).resolve()
    if source is not None and source.path != root:
        return ToolResult.failure("Doğrulanmış kaynak arama yoluyla eşleşmiyor.")

    if not root.exists():
        return ToolResult.failure(f"Yol yok: {root}")
    if len(pattern) > MAX_REGEX_PATTERN_CHARS or _UNSAFE_REGEX.search(pattern):
        return ToolResult.failure(
            "Regex deseni güvenli sınırı aşıyor veya patolojik geri izleme riski taşıyor; "
            "daha kısa ve basit bir desen dene."
        )
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return ToolResult.failure(f"Geçersiz regex: {exc}")

    hits: list[str] = []
    per_file: dict[str, tuple[int, str]] = {}
    scan = _SearchScan(context=context, started=time.monotonic())
    for path in _searchable_files(root, scan):
        for number, line in _matching_lines(path, regex, scan, source=source):
            gosterim = display_path(context, path)
            metin = _truncate_utf8(redact(line.strip()), MAX_SEARCH_LINE_BYTES)
            hits.append(f"{gosterim}:{number}: {metin}")
            sayac, ilk = per_file.get(gosterim, (0, f"{number}: {metin}"))
            per_file[gosterim] = (sayac + 1, ilk)
            if len(hits) >= MAX_SEARCH_HITS:
                return ToolResult.failure(
                    "\n".join(_summarize(per_file))
                    + f"\n… ({MAX_SEARCH_HITS}+ eşleşme; sonuç kısmidir, deseni daraltın)",
                    structured={"localization_candidates": tuple(scan.localization_candidates)},
                )
    if len(hits) > MAX_DETAILED_HITS:
        return _bounded_result(_summarize(per_file), scan, _empty_note("eşleşme yok", root))
    return _bounded_result(hits, scan, _empty_note("eşleşme yok", root))


def _summarize(per_file: dict[str, tuple[int, str]]) -> list[str]:
    """Çok eşleşmede dosya başına TEK satır.

    SWE-agent'ın ölçümü: her eşleşmeyi ayrı ayrı göstermek modeli şaşırtıyor; hangi
    dosyada kaç eşleşme olduğu ve ilk örnek, sonraki adımı seçmeye yeter. Ayrıntı
    gerekiyorsa model dosyayı `read_file` ile açar.
    """
    return [
        f"{path}: {sayac} eşleşme (ilk — {ilk})" for path, (sayac, ilk) in sorted(per_file.items())
    ]


def glob_matcher(pattern: str) -> Callable[[str], bool]:
    """Köke göreli POSIX yolu için glob eşleştiricisi döndür.

    `Path.match` KULLANILMAZ. Ölçüldü (29 Eylül, Python 3.11): `**`'ı tek klasör
    sayıyor; `**/lib/mcp/**/*.ts` ne `lib/mcp/server.ts`'i ne de derindeki
    dosyaları buldu, model 36 dakika aynı aramayı tekrarladı. Kurallar yaygın
    araçlarla (ripgrep, gitignore) aynıdır:

    - `**/` sıfır ya da daha çok klasör, `*` tek klasör içinde her şey, `?` tek
      karakter, `[abc]` karakter kümesi, `{ts,tsx}` seçenekler.
    - Eğik çizgisiz desen (`*.ts`, `mcp`) her derinlikte ADLA eşleşir: dosya adıyla
      ya da yoldaki bir KLASÖR adıyla. Model klasör bulmak için `glob("mcp")`
      diyor; eskiden yalnız dosya adına bakıldığı için boş dönüyordu.
    - Eğik çizgili desen köke göredir; ayrıca herhangi bir alt klasörden de
      başlayabilir (`lib/x/*.ts`, `src/lib/x/a.ts`'i de bulur) — eski davranış.
    """
    desen = pattern.strip().removeprefix("./")
    if "/" not in desen:
        ad = _glob_regex(desen)
        return lambda relative: any(ad.fullmatch(part) for part in relative.split("/"))
    tam = _glob_regex(desen)
    herhangi = _glob_regex("**/" + desen.removeprefix("**/"))
    return lambda relative: bool(tam.fullmatch(relative) or herhangi.fullmatch(relative))


def _glob_regex(pattern: str) -> re.Pattern[str]:
    """Glob desenini düzenli ifadeye çevir (`**` klasörler arası geçer)."""
    parca: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            parca.append("(?:[^/]+/)*")
            i += 3
        elif pattern.startswith("**", i):
            parca.append(".*")
            i += 2
        elif pattern[i] == "*":
            parca.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            parca.append("[^/]")
            i += 1
        elif pattern[i] == "[" and (kapanis := pattern.find("]", i + 1)) > i + 1:
            kume = pattern[i + 1 : kapanis].replace("\\", "\\\\")
            if kume.startswith("!"):
                kume = "^" + kume[1:]
            parca.append(f"[{kume}]")
            i = kapanis + 1
        elif pattern[i] == "{" and (kapanis := pattern.find("}", i + 1)) > i:
            secenekler = pattern[i + 1 : kapanis].split(",")
            parca.append("(?:" + "|".join(re.escape(s) for s in secenekler) + ")")
            i = kapanis + 1
        else:
            parca.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(parca), re.DOTALL)


def glob_files(args: ToolArgs, context: ToolContext) -> ToolResult:
    pattern = require_str(args, "pattern")
    root = resolve_path(context, optional_str(args, "path", ".")).resolve()

    if not root.exists():
        return ToolResult.failure(f"Yol yok: {root}")

    # MUTLAK desen `Path.glob`'da ham `NotImplementedError` fırlatır ve model
    # ekranda Python istisnası görür — ne olduğunu ne yapacağını anlamaz.
    # Ölçüldü: model `glob("/*")` çağırdı, araç çöktü ve tur "ilerleme yok" ile
    # öldü. Desen köke GÖRELİDİR; mutlak yol için `path` alanı vardır.
    if pattern.startswith("/") or (len(pattern) > 1 and pattern[1] == ":"):
        return ToolResult.failure(
            f"'{pattern}' mutlak bir yol. glob deseni arama köküne GÖRELİ olmalı "
            "(ör. '**/*.tsx'). Başka bir dizinde arayacaksan 'path' alanını kullan."
        )

    matches: list[str] = []
    scan = _SearchScan(context=context, started=time.monotonic())
    matcher = glob_matcher(pattern)
    for path in _searchable_files(root, scan, include_secret_names=True):
        relative = path.relative_to(root) if root.is_dir() else Path(path.name)
        if not matcher(relative.as_posix()):
            continue
        matches.append(display_path(context, path))
        if len(matches) >= MAX_GLOB_MATCHES:
            scan.stopped = f"{MAX_GLOB_MATCHES} glob sonucu sınırına ulaştı"
            break
    return _bounded_result(matches, scan, _empty_note("eşleşen dosya yok", root))


# --------------------------------------------------------------------------- #


def _is_skipped(path: Path, anchor: Path) -> bool:
    """Dosya aramadan hariç mi? Kural köke GÖRELİ bileşenlere bakar.

    Ölçüldü (29 Ekim): MUTLAK yolun tüm bileşenlerine bakılıyordu; proje `~/claude/proje`
    ya da `~/.config/x/proje` altındaysa HER dosya sessizce atlanıyordu. Kökün
    atalarında yalnız kimlik deposu klasörleri (.ssh, .aws, .azure, .gnupg) engeller.
    """
    if path.is_symlink():
        return True
    if any(part.casefold() in _CREDENTIAL_STORE_DIRECTORIES for part in anchor.parts):
        return True
    if anchor.name.casefold() in _PROFILE_DIRECTORIES:
        return True
    return any(_is_skipped_directory_name(part) for part in path.relative_to(anchor).parts[:-1])


def _is_skipped_directory_name(name: str) -> bool:
    return name.casefold() in _SKIP_DIRECTORY_NAMES


def _is_secret_file(path: Path) -> bool:
    """Arama çıktısına olası kimlik bilgisi dosyalarını hiç sokma.

    Kaynak kod uzantılı dosyalar (`auth.py`, `use-auth.ts`, `settings.py`) ad kalıbına
    takılmaz; çıktıdaki sır değerlerini ayrıca `redact` maskeler.
    """
    name = path.name.casefold()
    if name == ".env" or name.startswith(".env.") or name in _SECRET_FILE_NAMES:
        return True
    if path.suffix.casefold() in _SECRET_FILE_EXTENSIONS:
        return True
    if path.suffix.casefold() in _SOURCE_EXTENSIONS:
        return False
    return (
        name == "settings"
        or name.startswith("settings.")
        or name.startswith("settings-")
        or _SECRET_FILE_STEM_RE.search(path.name) is not None
    )


#: Dışarıdan (öğretmen gibi üçüncü taraf modellere gidecek içerik seçilirken) kullanılan ad.
is_secret_file = _is_secret_file


def is_searchable_source(path: Path, root: Path) -> bool:
    """Sembol adaptörü de aramanın kimlik deposu ve gizli dosya sınırını paylaşır."""
    return path.is_relative_to(root) and not _is_skipped(path, root) and not _is_secret_file(path)


def _truncate_utf8(text: str, max_bytes: int) -> str:
    """UTF-8 çıktıyı byte sınırında, geçerli karakter sınırında kes."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _searchable_files(
    root: Path, scan: _SearchScan, *, include_secret_names: bool = False
) -> Iterator[Path]:
    """Aranabilir dosyalar. `include_secret_names` yalnız ADLARIN listelenmesi içindir
    (glob): içerik okunmaz, bu yüzden gizli olabilecek dosyanın adı da görünür."""
    anchor = root.parent if root.is_file() else root
    if root.is_file():
        candidates: Iterator[Path] = iter((root,))
    else:

        def walk() -> Iterator[Path]:
            for current, directories, files in os.walk(root, followlinks=False):
                directories[:] = sorted(
                    name for name in directories if not _is_skipped_directory_name(name)
                )
                for name in sorted(files):
                    yield Path(current) / name

        candidates = walk()
    for path in candidates:
        if scan.should_stop():
            return
        scan.candidates += 1
        if _is_skipped(path, anchor):
            continue
        if _is_secret_file(path) and not include_secret_names:
            scan.skipped_secret_files += 1
            continue
        try:
            if path.stat().st_size > MAX_SEARCHABLE_FILE_BYTES:
                continue
        except OSError:
            continue
        yield path


def _matching_lines(
    path: Path, regex: re.Pattern[str], scan: _SearchScan, *, source: SearchSource | None = None
) -> Iterator[tuple[int, str]]:
    if source is not None:
        if source.path != path:
            return
        data = source.text.encode("utf-8")
    else:
        root = scan.context.root.resolve()
        if not path.is_relative_to(root):
            root = path.parent
        source_bytes = read_scoped_source(
            root, path.relative_to(root), max_bytes=MAX_SEARCHABLE_FILE_BYTES
        )
        if source_bytes is None:
            return
        data = source_bytes
    if len(data) > MAX_SEARCH_SCAN_BYTES:
        scan.truncated_files += 1
    text = data[:MAX_SEARCH_SCAN_BYTES].decode("utf-8", errors="ignore")
    for number, line in enumerate(text.splitlines(), 1):
        if scan.should_stop():
            return
        if len(line.encode("utf-8")) > MAX_SEARCH_LINE_BYTES:
            scan.oversized_lines += 1
            line = _truncate_utf8(line, MAX_SEARCH_LINE_BYTES)
        if regex.search(line):
            _record_source(scan, path, data, number)
            yield number, line


def _record_source(scan: _SearchScan, path: Path, source: bytes, line_number: int) -> None:
    """Eşleşmenin okunduğu aynı güvenli baytların özetini taşı."""
    root = scan.context.root.resolve()
    if not path.is_relative_to(root):
        return
    relative = path.relative_to(root).as_posix()
    if any(candidate["path"] == relative for candidate in scan.localization_candidates):
        return
    if len(scan.localization_candidates) >= MAX_LOCALIZATION_CANDIDATES:
        return
    scan.localization_candidates.append(
        {
            "path": relative,
            "symbol": localization_symbol(
                source.decode("utf-8", errors="ignore"), line_number, path
            ),
            "source_digest": hashlib.sha256(source).hexdigest(),
        }
    )
