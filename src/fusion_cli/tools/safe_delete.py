"""Geri alınabilir silme — Fusion hiçbir klasörü kalıcı olarak silmez.

Ölçülen zarar (1 Ekim 2026): kullanıcının "bu projeyi sil" isteğinde Fusion
`~/Desktop/01-Projeler` altındaki projelerin neredeyse tamamını sildi. Çöp boştu,
yedek yoktu; tek bir proje rastlantısal bir yedekten kurtarıldı.

Kurallar:

1. **Sade silme komutu çöpe taşınır.** `rm -rf <yol>` (joker dahil: `rm -rf ./*`)
   kalıcı silmek yerine Fusion çöpüne TAŞINIR (aynı diskte anlık). `fusion cop` ile
   geri alınır.
2. **Kullanıcı silmek isterse silinir.** Masaüstü, proje kökünün üst klasörü ya da
   içinde birden çok proje olan klasör REDDEDİLMEZ; onay kartında DİKKAT notuyla
   gösterilir ve otomatik kipte bile sorulur (`caution_reason`). Kullanıcı 2 Ekim'de
   açıkça istedi: "gerçekten bir şey silmek istersem silemeyecek miyim".
3. **Yalnız iki yer hiç silinmez:** dosya sisteminin kökü ve ev dizininin kendisi
   (`forbidden_reason`) — ikisi de çöpe taşınamaz (çöp onların içindedir).
"""

from __future__ import annotations

import json
import posixpath
import re
import shlex
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from ..core.errors import FusionError

#: Kök komutu `rm` olan, özyinelemeli silme içeren ama sade olmayan komutlar.
_RECURSIVE_DELETE = re.compile(
    r"\brm\s+(-[a-zA-Z]*\s+)*-[a-zA-Z]*[rR]|\bfind\b.*\s-delete\b|\bfind\b.*-exec\s+rm\b|"
    r"\bxargs\b.*\brm\b|\brmtree\b|\bgit\s+clean\s+-[a-zA-Z]*[fdx]"
)
#: Sade komutta bulunmaması gereken kabuk işleçleri. Joker (`*?[]`) burada YOK:
#: `rm -rf ./*` Fusion tarafından genişletilip her öğe ayrı ayrı çöpe taşınır.
_SHELL_META = re.compile(r"[;&|<>`$()\n{}]")
#: Kabuğun genişleteceği joker karakterleri.
_GLOB_CHARS = frozenset("*?[")
#: `rm`'in kabul edilen seçenek harfleri.
_RM_FLAGS = frozenset("rRfvid")
#: Ev dizini altında hiçbir zaman silinmeyen standart klasörler.
_PROTECTED_HOME_DIRS = (
    "Desktop", "Documents", "Downloads", "Library", "Pictures", "Movies", "Music",
    "Applications", "Public", "Sites", ".ssh", ".config", ".local",
)  # fmt: skip
#: İçinde bu kadar ya da daha fazla proje olan klasör "proje deposu" sayılır.
MULTI_PROJECT_THRESHOLD = 2
#: Proje olduğunu gösteren dosyalar.
_PROJECT_MARKERS = (".git", "package.json", "pyproject.toml", "composer.json", "project.godot")
#: Fusion çöpündeki girdiler bu kadar gün sonra temizlenir. macOS Çöp Sepeti'nin
#: "30 gün sonra öğeleri sil" seçeneğiyle aynı süre.
TRASH_RETENTION_DAYS = 30
_MANIFEST = "fusion-cop.json"


class DeleteRefusedError(FusionError):
    """Silme reddedildi; mesaj modele/kullanıcıya olduğu gibi gösterilir."""


@dataclass(frozen=True, slots=True)
class TrashEntry:
    id: str
    original: Path
    stored: Path
    deleted_at: float


def simple_rm_targets(command: str) -> tuple[str, ...] | None:
    """Komut düz bir `rm [-seçenek] yol...` ise hedefleri, değilse None.

    Jokerli hedef (`./*`) olduğu gibi döner; `expand_targets` onu kabuk gibi açar.
    """
    if _SHELL_META.search(command):
        return None
    try:
        parts = shlex.split(command)
    except ValueError:
        return None
    if not parts or parts[0].rsplit("/", 1)[-1] != "rm":
        return None
    targets: list[str] = []
    options_done = False
    for part in parts[1:]:
        if not options_done and part == "--":
            options_done = True
        elif not options_done and part.startswith("-") and len(part) > 1:
            if not set(part[1:]) <= _RM_FLAGS:
                return None
        elif _GLOB_CHARS & set(part.rpartition("/")[0]):
            # `*/build`: joker klasör bileşeninde; kabuğa bırakılır (sade değil).
            return None
        else:
            targets.append(part)
    return tuple(targets) if targets else None


def expand_targets(targets: tuple[str, ...], cwd: Path) -> list[Path]:
    """Hedefleri kabuğun yapacağı gibi aç: göreli yol `cwd`'ye, joker eşleşmelere.

    Kabuk gibi gizli dosyalar `*` ile eşleşmez; eşleşmeyen joker olduğu gibi kalır
    (rm de "yok" der).
    """
    paths: list[Path] = []
    for raw in targets:
        # `..` metin olarak çözülür (bağ izlenmez): `rm ..` bağın hedefini değil
        # üst klasörü taşır ve çöpteki adı ".." olmaz.
        base = Path(posixpath.normpath(cwd / Path(raw).expanduser()))
        matches = _shell_glob(base) if _GLOB_CHARS & set(base.name) else []
        paths.extend(matches)
        if not matches:
            paths.append(base)
    return paths


def _shell_glob(base: Path) -> list[Path]:
    """Son bileşendeki jokeri kabuk gibi aç: `*` noktayla başlayan adlarla eşleşmez."""
    hidden_ok = base.name.startswith(".")
    return sorted(
        match
        for match in base.parent.glob(base.name)
        if hidden_ok or not match.name.startswith(".")
    )


def is_complex_recursive_delete(command: str) -> bool:
    """Özyinelemeli silme var ama sade biçimde değil mi?"""
    return bool(_RECURSIVE_DELETE.search(command)) and simple_rm_targets(command) is None


def forbidden_reason(path: Path, home: Path, trash_root: Path | None = None) -> str | None:
    """Bu yol HİÇBİR koşulda silinemez mi? Yalnız kök, ev dizini ve çöpün kendisi."""
    target = path.resolve()
    if target == Path(target.anchor) or target == home.resolve():
        return "dosya sisteminin kökü ya da ev dizininin kendisi"
    if trash_root is not None and trash_root.resolve().is_relative_to(target):
        return "Fusion çöpünü içeren klasör (kendi içine taşınamaz)"
    return None


def caution_reason(path: Path, root: Path, home: Path) -> str | None:
    """Silinebilir ama kullanıcının bilerek onaylaması gereken yer mi? Gerekçe ya da None.

    Bu bir RET değildir: onay kartında DİKKAT notu olur ve otomatik kip sorar.
    """
    target = path.resolve()
    home = home.resolve()
    resolved_root = root.resolve()
    if target.parent == home and target.name in _PROTECTED_HOME_DIRS:
        return f"ev dizinindeki standart klasör (~/{target.name})"
    if target == resolved_root:
        return "çalışılan klasörün KENDİSİ"
    if resolved_root.is_relative_to(target):
        return "çalışılan klasörün ÜST klasörü (içinde başka projeler olabilir)"
    if not target.is_relative_to(resolved_root):
        return "çalışılan klasörün DIŞINDA"
    if target.is_dir() and _project_count(target) >= MULTI_PROJECT_THRESHOLD:
        return "içinde birden çok proje bulunan klasör"
    return None


def project_folders(folder: Path, depth: int = 2) -> list[Path]:
    """Klasörün altındaki proje klasörleri (iki kat derine bakılır)."""
    try:
        children = sorted(
            child for child in folder.iterdir() if child.is_dir() and not child.is_symlink()
        )
    except OSError:
        return []
    found: list[Path] = []
    for child in children:
        if child.name in ("node_modules", ".git") or child.name.startswith("."):
            continue
        if any((child / marker).exists() for marker in _PROJECT_MARKERS):
            found.append(child)
        elif depth > 1:
            found.extend(project_folders(child, depth - 1))
    return found


def is_container_root(root: Path, home: Path) -> bool:
    """Kök tek bir proje değil, projelerin durduğu bir klasör mü?"""
    resolved = root.resolve()
    home = home.resolve()
    if resolved == home or (resolved.parent == home and resolved.name in _PROTECTED_HOME_DIRS):
        return True
    if any((resolved / marker).exists() for marker in _PROJECT_MARKERS):
        return False
    return len(project_folders(resolved)) >= MULTI_PROJECT_THRESHOLD


def _project_count(folder: Path, depth: int = 2) -> int:
    """Klasörün altındaki proje sayısı (iki kat derine bakılır: `01-Projeler/projeler/X`)."""
    try:
        children = [
            child for child in folder.iterdir() if child.is_dir() and not child.is_symlink()
        ]
    except OSError:
        return 0
    count = 0
    for child in children:
        if child.name in ("node_modules", ".git"):
            continue
        if any((child / marker).exists() for marker in _PROJECT_MARKERS):
            count += 1
        elif depth > 1:
            count += _project_count(child, depth - 1)
    return count


def move_to_trash(
    targets: tuple[str, ...], *, cwd: Path, root: Path, home: Path, trash_root: Path
) -> tuple[list[TrashEntry], list[str]]:
    """Hedefleri Fusion çöpüne taşı; (taşınanlar, atlananlar) döner.

    Yasak bir hedef varsa HİÇBİRİ taşınmaz: yarım kalan toplu silme kullanıcıyı
    neyin gidip neyin kaldığını çözmeye zorlar. `root` imza uyumu için durur;
    dikkat gerektiren yerler onay aşamasında (`caution_reason`) sorulur.
    """
    del root
    paths = expand_targets(targets, cwd)
    for path in paths:
        reason = forbidden_reason(path, home, trash_root)
        if reason is not None:
            raise DeleteRefusedError(
                f"SİLME REDDEDİLDİ: {path} — {reason}. Bu yol çöpe taşınamaz. Silinmesi "
                "gereken bir klasör ya da dosyaysa onun TAM yolunu ver."
            )
    _purge_expired(trash_root)
    moved: list[TrashEntry] = []
    missing: list[str] = []
    for path in paths:
        if not path.exists() and not path.is_symlink():
            missing.append(str(path))
            continue
        entry_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        folder = trash_root / entry_id
        folder.mkdir(parents=True, exist_ok=True)
        stored = folder / path.name
        shutil.move(str(path), str(stored))
        entry = TrashEntry(entry_id, path.resolve(strict=False), stored, time.time())
        (folder / _MANIFEST).write_text(
            json.dumps(
                {"asil_yol": str(entry.original), "silinme": entry.deleted_at},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        moved.append(entry)
    return moved, missing


def list_trash(trash_root: Path) -> list[TrashEntry]:
    entries: list[TrashEntry] = []
    if not trash_root.is_dir():
        return entries
    for folder in sorted(trash_root.iterdir(), reverse=True):
        manifest = folder / _MANIFEST
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        stored = next((item for item in folder.iterdir() if item.name != _MANIFEST), None)
        if stored is None:
            continue
        entries.append(
            TrashEntry(folder.name, Path(data["asil_yol"]), stored, float(data["silinme"]))
        )
    return entries


def restore(trash_root: Path, entry_id: str) -> Path:
    """Çöpteki girdiyi asıl yerine geri koy; hedef doluysa ezmez."""
    entry = next((item for item in list_trash(trash_root) if item.id == entry_id), None)
    if entry is None:
        raise DeleteRefusedError(f"Çöpte böyle bir girdi yok: {entry_id}")
    if entry.original.exists():
        raise DeleteRefusedError(f"Asıl yerde zaten bir şey var, ezilmedi: {entry.original}")
    entry.original.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(entry.stored), str(entry.original))
    shutil.rmtree(trash_root / entry.id, ignore_errors=True)
    return entry.original


def _purge_expired(trash_root: Path) -> None:
    limit = time.time() - TRASH_RETENTION_DAYS * 86_400
    for entry in list_trash(trash_root):
        if entry.deleted_at < limit:
            shutil.rmtree(trash_root / entry.id, ignore_errors=True)


#: Önizlemede sayılacak en fazla dosya; daha büyük klasör "N+ öğe" diye gösterilir.
