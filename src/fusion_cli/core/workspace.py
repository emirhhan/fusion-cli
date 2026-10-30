"""İzole çalışma alanı — aynı adımı birden çok kez denemenin ön koşulu.

Paralel deneme (test-time scaling) bir adımı N kez koşturup kazananı kanıtla
seçmeyi ister. Bu, her denemenin BİRBİRİNİ görmeyen bir kopyada çalışmasını
gerektirir: aksi halde ikinci deneme birincinin yarım bıraktığı dosyaların üstüne
yazar ve "hangi aday kazandı" sorusu anlamsızlaşır.

İzolasyon git'e BAĞLI DEĞİLDİR. Kaynak dizin kopyalanır; böylece Git deposundaki
commitlenmemiş ve izlenmeyen dosyalar da adayın gördüğü başlangıç durumuna girer.

Kazanan aday `apply()` ile asıl projeye taşınır. Seçim yapılmadan HİÇBİR aday asıl
projeye dokunmaz — bu, paralel denemenin güvenlik sözleşmesidir.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path

from .changeset import ChangeSet
from .errors import WorkspaceConflictError

#: Kopyalanmayan dizinler: üretilmiş çıktı ve bağımlılık ağaçları denemeyi
#: yavaşlatır ve kazananı seçerken hiçbir şey söylemez.
_SKIP = frozenset(
    {".git", ".venv", "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache", "target"}
)


@dataclass
class IsolatedWorkspace:
    """Bir denemenin kendi kopyası."""

    root: Path
    origin: Path
    uses_worktree: bool = False
    baseline_hashes: dict[Path, str] = field(default_factory=dict)
    _applied: bool = field(default=False, init=False)

    def changed_files(self) -> tuple[Path, ...]:
        """Kopyada adayın BAŞLANGIÇ durumundan farklı olan dosyalar."""
        farkli: list[Path] = []
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or path.is_symlink() or _skipped(path.relative_to(self.root)):
                continue
            goreli = path.relative_to(self.root)
            if self.baseline_hashes.get(goreli) != _digest(path):
                farkli.append(goreli)
        return tuple(farkli)

    def removed_files(self) -> tuple[Path, ...]:
        """Adayın başlangıç durumunda olup kopyada artık bulunmayan dosyalar."""
        return tuple(
            relative
            for relative in sorted(self.baseline_hashes)
            if not (self.root / relative).is_file()
        )

    def apply(self, *, changes: ChangeSet | None = None) -> tuple[Path, ...]:
        """Kazanan adayın değişikliklerini asıl projeye taşı ve geri almaya kaydet."""
        degisenler = self.changed_files()
        silinenler = self.removed_files()
        _validate_layout(self.origin, degisenler)
        for goreli in (*degisenler, *silinenler):
            mevcut = self.origin / goreli
            mevcut_ozet = _digest(mevcut) if mevcut.is_file() else None
            if mevcut_ozet != self.baseline_hashes.get(goreli):
                raise WorkspaceConflictError(
                    f"İzole aday çalışırken asıl dosya değişti: {goreli}. "
                    "Kullanıcının değişikliği korunarak aday uygulanmadı."
                )
        for goreli in (*degisenler, *silinenler):
            if changes is not None and not changes.record(self.origin / goreli):
                raise WorkspaceConflictError(
                    f"Geri alma kaydı oluşturulamadı: {goreli}. Aday uygulanmadı."
                )
        for goreli in degisenler:
            hedef = self.origin / goreli
            hedef.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.root / goreli, hedef)
        for goreli in silinenler:
            (self.origin / goreli).unlink(missing_ok=True)
        self._applied = True
        return (*degisenler, *silinenler)


@contextmanager
def isolate(root: Path, *, name: str) -> Iterator[IsolatedWorkspace]:
    """Proje için izole bir çalışma alanı aç ve çıkışta temizle."""
    parent = Path(tempfile.mkdtemp(prefix=f"fusion-deneme-{name}-"))
    hedef = parent / "alan"
    shutil.copytree(root, hedef, symlinks=True, ignore=_kopya_disi(root))
    baseline = {
        path.relative_to(hedef): _digest(path)
        for path in hedef.rglob("*")
        if path.is_file() and not path.is_symlink() and not _skipped(path.relative_to(hedef))
    }
    alan = IsolatedWorkspace(root=hedef, origin=root, baseline_hashes=baseline)
    try:
        yield alan
    finally:
        shutil.rmtree(parent, ignore_errors=True)


def _kopya_disi(root: Path) -> Callable[[str, list[str]], set[str]]:
    """Kopyada atlanacaklar: `_SKIP` dizinleri + kökün DIŞINA çıkan sembolik bağlar.

    Bağ kopyada bağ olarak kalırsa aday onun içinden yazarak ASIL (kök dışı) dosyayı
    değiştirir ve "seçim yapılmadan asıl projeye dokunulmaz" sözleşmesi bozulur.
    Ölçüldü (30 Ekim): `symlinks=True` mutlak/dışa giden bağları aynen taşıyordu.
    Yalnız kök İÇİNE giden GÖRELİ bağlar korunur (kopyanın kendi içinde çözülür).
    """
    kok = root.resolve()
    adlar = shutil.ignore_patterns(*_SKIP)

    def ignore(dizin: str, isimler: list[str]) -> set[str]:
        atlanan = set(adlar(dizin, isimler))
        for isim in isimler:
            yol = Path(dizin) / isim
            if not yol.is_symlink() or isim in atlanan:
                continue
            hedef = yol.readlink()
            if hedef.is_absolute() or not (yol.parent / hedef).resolve().is_relative_to(kok):
                atlanan.add(isim)
        return atlanan

    return ignore


def _skipped(relative: Path) -> bool:
    return any(part in _SKIP for part in relative.parts)


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _validate_layout(origin: Path, changed: tuple[Path, ...]) -> None:
    """Dosya/dizin ve symlink tür geçişlerini herhangi bir yazmadan önce reddet."""
    for relative in changed:
        target = origin / relative
        invalid_target = target.is_symlink() or (target.exists() and not target.is_file())
        parent = target.parent
        invalid_parent = False
        while parent != origin:
            if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                invalid_parent = True
                break
            parent = parent.parent
        if invalid_target or invalid_parent:
            raise WorkspaceConflictError(
                f"İzole aday desteklenmeyen dosya/dizin tür değişimi istedi: {relative}. "
                "Aday uygulanmadı."
            )
