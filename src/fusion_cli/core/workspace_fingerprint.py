"""Çalışma alanı parmak izi: bir kabuk komutu dosya DEĞİŞTİRDİ mi?

(`runtime.shell_workspace_fingerprint`)

Tanınmayan bir program (`python3 -m paket.cli listele`) komut metninden okunarak
"zararsız" ya da "zararlı" diye ayırt edilemez. Eskiden bu komutlar temkinli olarak
mutasyon sayılıyordu ve testler bundan ÖNCE geçmişse kanıt bayatlıyordu.

Ölçüldü (30 Ekim, g3/y3): `pytest` geçti, ardından modelin elle denediği
`python3 -m gorevler.cli listele` hiçbir dosyayı değiştirmediği hâlde mutasyon sayıldı;
tur "⚠ Görev kısmi kaldı" bitti ve doğru "testler geçti" iddiası GEÇERSİZ ilan edildi.

Çözüm: komuttan hemen önce ve sonra proje kökünün parmak izi (göreli yol → boyut,
mtime_ns) alınır ve karşılaştırılır. Aynıysa komut dosya değiştirmemiştir; farklıysa
değişen dosyalar adıyla bilinir.

Sınırlar (bilinçli, hepsinde temkinli eski davranışa dönülür):
- Gürültü dizinleri (`.git`, `node_modules`, `.venv`, `__pycache__`, `dist`, `build`,
  `.fusion`, önbellekler) gezilmez.
- Dosya sayısı ve süre sınırı aşılırsa ölçüm yapılmaz (`None`).
- PROJE KÖKÜ DIŞINA yazan komut (ör. `~/.gorevler.json`) parmak izinde GÖRÜNMEZ.

Yalnız stdlib kullanır (`core` katmanı).
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

#: Bir parmak izine girecek en çok dosya; aşılırsa ölçüm yapılmaz.
MAX_FILES = 20_000
#: Bir parmak izi için en uzun süre (sn); aşılırsa ölçüm yapılmaz.
MAX_SECONDS = 0.3
#: Zaman denetimi bu kadar girdide bir yapılır (her dosyada saat okumamak için).
_CLOCK_EVERY = 256
#: Ajanın değişikliği sayılmayan, derleme/önbellek/sürüm denetimi dizinleri.
NOISE_DIRS = frozenset(
    {".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
     ".fusion", ".mypy_cache", ".ruff_cache", ".pytest_cache", ".tox", ".nox", ".next",
     ".nuxt", ".svelte-kit", ".turbo", ".parcel-cache", ".cache", ".gradle", ".eggs",
     "htmlcov"}
)  # fmt: skip
#: Gürültü dosya adları ve uzantıları (yorumlayıcı/işletim sistemi artığı).
_NOISE_FILES = frozenset({".DS_Store", ".coverage"})
_NOISE_SUFFIXES = (".pyc", ".pyo")
_MAX_NAMED_CHANGES = 5

#: Dosya yolu → (boyut, mtime_ns).
Fingerprint = Mapping[str, tuple[int, int]]

# Arka plana atan komut: tek `&` (`&&`, `>&`, `&>` değil), `nohup`, `setsid`, `disown`.
_QUOTED = re.compile(r"'[^']*'|\"(?:\\.|[^\"\\])*\"")
_BACKGROUND = re.compile(r"(?<![&>|])&(?![&>])|\b(?:nohup|setsid|disown)\b")


def launches_background_process(command: str) -> bool:
    """Komut komut bitse de süren bir süreç bırakabilir mi (`&`, `nohup`, `setsid`)?

    Süren süreç komut bittikten SONRA da dosya yazabilir; bu yüzden "önce/sonra"
    karşılaştırması onun için güvenilir değildir.
    """
    return bool(_BACKGROUND.search(_QUOTED.sub(" ", command)))


def _is_noise_dir(name: str, path: str) -> bool:
    if name in NOISE_DIRS or name.endswith(".egg-info"):
        return True
    # Rust `target/` yalnız Cargo projesinde gürültüdür; başka yerde gerçek dizin olabilir.
    return name == "target" and (Path(path).parent / "Cargo.toml").exists()


def take_fingerprint(
    root: Path,
    *,
    max_files: int = MAX_FILES,
    max_seconds: float = MAX_SECONDS,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, tuple[int, int]] | None:
    """Kökün parmak izi; sınır aşılır ya da kök okunamazsa `None` (ölçülemedi).

    Sembolik bağlar TAKİP EDİLMEZ: bağın kendisi tek girdidir (kök dışına çıkılmaz).
    """
    deadline = clock() + max_seconds
    files: dict[str, tuple[int, int]] = {}
    base = str(root)
    stack = [base]
    seen = 0
    while stack:
        directory = stack.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    seen += 1
                    if seen % _CLOCK_EVERY == 0 and clock() > deadline:
                        return None
                    if _visit(entry, base, files, stack) and len(files) > max_files:
                        return None
        except OSError:
            if directory == base:
                return None  # Kök okunamadı: ölçüm yok.
            continue  # Alt dizin kayboldu/izin yok: o dal atlanır.
    return files


def _visit(
    entry: os.DirEntry[str], base: str, files: dict[str, tuple[int, int]], stack: list[str]
) -> bool:
    """Bir girdiyi işle; dosya eklendiyse True."""
    try:
        if entry.is_dir(follow_symlinks=False):
            if not _is_noise_dir(entry.name, entry.path):
                stack.append(entry.path)
            return False
        if entry.name in _NOISE_FILES or entry.name.endswith(_NOISE_SUFFIXES):
            return False
        info = entry.stat(follow_symlinks=False)
    except OSError:
        return False  # Girdi gezinirken silindi: yarış, sonraki karşılaştırmada görünür.
    files[os.path.relpath(entry.path, base)] = (info.st_size, info.st_mtime_ns)
    return True


def changed_paths(before: Fingerprint, after: Fingerprint) -> tuple[str, ...]:
    """Eklenen, silinen ya da boyutu/zamanı değişen yollar (sıralı)."""
    return tuple(
        sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path))
    )


@dataclass(frozen=True, slots=True)
class WorkspaceEffect:
    """Bir kabuk komutunun proje kökündeki ölçülen etkisi.

    `changed`: `()` = hiçbir dosya değişmedi; dolu = değişen yollar; `None` = ölçülemedi
    (süre/dosya sınırı, arka plan süreci); bu durumda komut TEMKİNLİ olarak dosya
    değiştirmiş sayılır.
    """

    changed: tuple[str, ...] | None
    #: Ölçülemediyse nedeni (iz için).
    reason: str = ""

    @property
    def is_unchanged(self) -> bool:
        return self.changed == ()

    @property
    def label(self) -> str:
        """İz/olay etiketi: "değişmedi" | "N dosya değişti: a, b" | "ölçülemedi: neden"."""
        if self.changed is None:
            return f"ölçülemedi: {self.reason}" if self.reason else "ölçülemedi"
        if not self.changed:
            return "değişmedi"
        adlar = ", ".join(self.changed[:_MAX_NAMED_CHANGES])
        fazla = len(self.changed) - _MAX_NAMED_CHANGES
        return f"{len(self.changed)} dosya değişti: {adlar}" + (f" (+{fazla})" if fazla > 0 else "")


def measure_effect(before: Fingerprint | None, root: Path) -> WorkspaceEffect:
    """Komut bittikten sonra ikinci parmak izini al ve öncekiyle karşılaştır."""
    if before is None:
        return WorkspaceEffect(None, "ilk parmak izi alınamadı (dosya/süre sınırı)")
    after = take_fingerprint(root)
    if after is None:
        return WorkspaceEffect(None, "ikinci parmak izi alınamadı (dosya/süre sınırı)")
    return WorkspaceEffect(changed_paths(before, after))


_CONTENT_CHUNK_BYTES = 65_536


def content_digest(paths: Iterable[Path], *, strict: bool = False) -> str:
    """Açıkça seçilmiş dosyaların adını ve içeriğini tek özette birleştir.

    Dosya yokluğu da kimliktir; okunamayan dosya başarıyla okunmuş sayılmaz.
    Sembolik bağın hedefi yerine bağın kendi değeri kullanılır.
    """
    digest = hashlib.sha256()
    for path in sorted(set(paths)):
        digest.update(str(path).encode())
        digest.update(b"\0")
        try:
            if path.is_symlink():
                digest.update(b"link:")
                digest.update(str(path.readlink()).encode())
            else:
                with path.open("rb") as stream:
                    while chunk := stream.read(_CONTENT_CHUNK_BYTES):
                        digest.update(chunk)
        except OSError as error:
            if strict and (not isinstance(error, FileNotFoundError) or path.is_symlink()):
                raise
            digest.update(f"okunamadi:{error.errno}".encode())
        digest.update(b"\0")
    return digest.hexdigest()
