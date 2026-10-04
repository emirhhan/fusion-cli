"""Kitaplık: yüklenen ve Fusion'ın oluşturduğu dosyaların kalıcı listesi (`kitaplik.*`).

Üç kaynak tek listede birleşir:

- **üretilen**: turda GERÇEKTEN değişen dosyalar (`FilesChanged` olayından; modelin
  iddiasından değil). Dosya yerinde durur, kitaplık yalnız yolunu bilir.
- **yüklenen**: kullanıcının kitaplığa eklediği dosya; kopyası kitaplık klasöründe durur.
- **görsel**: uygulama içi galerideki görseller (bkz. `image_flows.gallery_dir`).

Kayıt defteri satır başına bir JSON nesnesidir; okurken son kayıt kazanır. Diskte
artık bulunmayan dosya listelenmez (silinmiş çıktıyı göstermek yanıltır).
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ..config.paths import user_data_dir
from ..core.events import Event, EventSink, FilesChanged
from .image_flows import gallery_dir

SOURCE_GENERATED = "uretilen"
SOURCE_UPLOADED = "yuklenen"
SOURCE_IMAGE = "gorsel"

#: Listenin üst sınırı. Arayüz tek ekranda gösterir; daha eskisi aramayla bulunur.
MAX_ITEMS = 500
#: Tek dosya yükleme sınırı. Kitaplık bir yedekleme aracı değildir; büyük dosya
#: kopyalamak diski sessizce doldurur (8 GB'lık makinede disk %93 doluyken ölçüldü).
MAX_UPLOAD_BYTES = 200 * 1024 * 1024

_KINDS: dict[str, frozenset[str]] = {
    "gorsel": frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".avif"}),
    "video": frozenset({".mp4", ".mov", ".webm", ".mkv"}),
    "belge": frozenset({".md", ".txt", ".pdf", ".docx", ".xlsx", ".pptx", ".csv", ".html"}),
    "kod": frozenset(
        {".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go", ".php", ".css", ".json", ".yaml"}
        | {".yml", ".toml", ".sh", ".sql", ".gd", ".java", ".kt", ".swift", ".c", ".cpp", ".h"}
    ),
}
KIND_OTHER = "diger"


def library_dir() -> Path:
    return user_data_dir() / "library"


def _index_path(base: Path) -> Path:
    return base / "kayitlar.jsonl"


def _uploads_dir(base: Path) -> Path:
    return base / "yuklenenler"


def kind_of(path: Path) -> str:
    suffix = path.suffix.lower()
    return next((kind for kind, suffixes in _KINDS.items() if suffix in suffixes), KIND_OTHER)


def _append(base: Path, entries: Iterable[dict[str, Any]]) -> None:
    lines = [json.dumps(entry, ensure_ascii=False) for entry in entries]
    if not lines:
        return
    base.mkdir(parents=True, exist_ok=True)
    with _index_path(base).open("a", encoding="utf-8") as index:
        index.write("\n".join(lines) + "\n")


def _read_index(base: Path) -> dict[str, dict[str, Any]]:
    """Yol → son kayıt. Bozuk satır atlanır; `kaldirildi` kaydı yolu düşürür."""
    try:
        lines = _index_path(base).read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    latest: dict[str, dict[str, Any]] = {}
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        path = entry.get("yol") if isinstance(entry, dict) else None
        if not isinstance(path, str):
            continue
        if entry.get("kaldirildi"):
            latest.pop(path, None)
        else:
            latest[path] = entry
    return latest


def record_generated(root: Path, paths: Iterable[str], directory: Path | None = None) -> int:
    """Turda değişen dosyaları kitaplığa yaz; kaydedilen dosya sayısını döndür."""
    stamp = time.time()
    entries = []
    for raw in paths:
        path = Path(raw)
        resolved = (path if path.is_absolute() else root / path).resolve()
        if resolved.is_file():
            entries.append(
                {"yol": str(resolved), "kaynak": SOURCE_GENERATED, "kok": str(root), "zaman": stamp}
            )
    _append(directory or library_dir(), entries)
    return len(entries)


def _unique_target(folder: Path, name: str) -> Path:
    target = folder / name
    stem, suffix = target.stem, target.suffix
    counter = 2
    while target.exists():
        target = folder / f"{stem}-{counter}{suffix}"
        counter += 1
    return target


def add_upload(data: dict[str, Any], directory: Path | None = None) -> dict[str, Any]:
    """Kullanıcının seçtiği dosyayı kitaplığa kopyala."""
    base = directory or library_dir()
    raw = data.get("yol")
    if not isinstance(raw, str) or not raw.strip():
        return {"ok": False, "metin": "Eklenecek dosyanın yolu gerekli."}
    source = Path(raw).expanduser()
    if not source.is_file():
        return {"ok": False, "metin": "Dosya bulunamadı."}
    try:
        if source.stat().st_size > MAX_UPLOAD_BYTES:
            return {"ok": False, "metin": "Dosya 200 MB sınırını aşıyor."}
        uploads = _uploads_dir(base)
        uploads.mkdir(parents=True, exist_ok=True)
        target = _unique_target(uploads, source.name)
        shutil.copyfile(source, target)
    except OSError as error:
        return {"ok": False, "metin": f"Dosya eklenemedi: {error}"}
    _append(base, [{"yol": str(target), "kaynak": SOURCE_UPLOADED, "zaman": time.time()}])
    return {"ok": True, "yol": str(target)}


def remove_entry(data: dict[str, Any], directory: Path | None = None) -> dict[str, Any]:
    """Kaydı listeden çıkar. Dosyanın kendisine dokunulmaz (silme ayrı bir karardır)."""
    base = directory or library_dir()
    raw = data.get("yol")
    if not isinstance(raw, str) or raw not in _read_index(base):
        return {"ok": False, "metin": "Kitaplıkta böyle bir kayıt yok."}
    _append(base, [{"yol": raw, "kaldirildi": True, "zaman": time.time()}])
    return {"ok": True}


def _item(path: Path, source: str, root: str = "") -> dict[str, Any] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    if not path.is_file():
        return None
    return {
        "yol": str(path),
        "ad": path.name,
        "tur": kind_of(path),
        "kaynak": source,
        "kok": root,
        "boyut": stat.st_size,
        "degisim": stat.st_mtime,
    }


def _gallery_items(gallery: Path) -> list[dict[str, Any]]:
    if not gallery.is_dir():
        return []
    images = (p for p in gallery.iterdir() if p.suffix.lower() in _KINDS["gorsel"])
    return [item for item in (_item(path, SOURCE_IMAGE) for path in images) if item]


def list_library(
    data: dict[str, Any], directory: Path | None = None, gallery: Path | None = None
) -> dict[str, Any]:
    """Kitaplığı listele: `tur` (gorsel|video|belge|kod|diger) ve `sorgu` ile süz."""
    base = directory or library_dir()
    kind = data.get("tur")
    query = data.get("sorgu")
    needle = query.strip().casefold() if isinstance(query, str) else ""
    indexed = (
        _item(Path(path), str(entry.get("kaynak", SOURCE_GENERATED)), str(entry.get("kok", "")))
        for path, entry in _read_index(base).items()
    )
    items = [item for item in indexed if item] + _gallery_items(gallery or gallery_dir())
    if isinstance(kind, str) and kind:
        items = [item for item in items if item["tur"] == kind]
    if needle:
        items = [item for item in items if needle in item["yol"].casefold()]
    items.sort(key=lambda item: item["degisim"], reverse=True)
    return {"ok": True, "dosyalar": items[:MAX_ITEMS], "toplam": len(items)}


class LibrarySink:
    """Olay akışını sarar; turda değişen dosyaları kitaplığa yazar.

    Kayıt bir yan etkidir: disk hatası turu düşürmez, olay yine iletilir.
    """

    def __init__(self, inner: EventSink, root: Path, directory: Path | None = None) -> None:
        self._inner = inner
        self._root = root
        self._directory = directory

    def handle(self, event: Event) -> None:
        if isinstance(event, FilesChanged):
            try:
                record_generated(self._root, event.paths, self._directory)
            except OSError as error:
                logging.getLogger(__name__).warning("Kitaplık kaydı yazılamadı: %s", error)
        self._inner.handle(event)
