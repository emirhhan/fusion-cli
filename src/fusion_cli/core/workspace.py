"""İzole çalışma alanı — aynı adımı birden çok kez denemenin ön koşulu.

Paralel deneme (test-time scaling) bir adımı N kez koşturup kazananı kanıtla
seçmeyi ister. Bu, her denemenin BİRBİRİNİ görmeyen bir kopyada çalışmasını
gerektirir: aksi halde ikinci deneme birincinin yarım bıraktığı dosyaların üstüne
yazar ve "hangi aday kazandı" sorusu anlamsızlaşır.

İzolasyon git'e BAĞLI DEĞİLDİR. Proje git olmayabilir, dosyalar untracked olabilir
ve kullanıcının bekleyen değişiklikleri bulunabilir; `changeset` modülünün aynı
gerekçesi burada da geçerlidir. Git varsa `worktree` kullanılır çünkü ucuzdur;
yoksa dizin kopyalanır.

Kazanan aday `apply()` ile asıl projeye taşınır. Seçim yapılmadan HİÇBİR aday asıl
projeye dokunmaz — bu, paralel denemenin güvenlik sözleşmesidir.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

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
    _applied: bool = field(default=False, init=False)

    def changed_files(self) -> tuple[Path, ...]:
        """Kopyada ASIL projeden farklı olan dosyalar."""
        farkli: list[Path] = []
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or _skipped(path.relative_to(self.root)):
                continue
            goreli = path.relative_to(self.root)
            hedef = self.origin / goreli
            if not hedef.is_file() or hedef.read_bytes() != path.read_bytes():
                farkli.append(goreli)
        return tuple(farkli)

    def apply(self) -> tuple[Path, ...]:
        """Kazanan adayın değişikliklerini asıl projeye taşı."""
        degisenler = self.changed_files()
        for goreli in degisenler:
            hedef = self.origin / goreli
            hedef.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.root / goreli, hedef)
        self._applied = True
        return degisenler


@contextmanager
def isolate(root: Path, *, name: str) -> Iterator[IsolatedWorkspace]:
    """Proje için izole bir çalışma alanı aç ve çıkışta temizle."""
    parent = Path(tempfile.mkdtemp(prefix=f"fusion-deneme-{name}-"))
    hedef = parent / "alan"
    worktree = _git_worktree(root, hedef)
    if not worktree:
        shutil.copytree(root, hedef, ignore=shutil.ignore_patterns(*_SKIP))
    alan = IsolatedWorkspace(root=hedef, origin=root, uses_worktree=worktree)
    try:
        yield alan
    finally:
        if worktree:
            _run_git(root, "worktree", "remove", "--force", str(hedef))
        shutil.rmtree(parent, ignore_errors=True)


def _git_worktree(root: Path, hedef: Path) -> bool:
    """Git deposuysa worktree aç; değilse ya da komut düşerse `False`."""
    if not (root / ".git").exists():
        return False
    sonuc = _run_git(root, "worktree", "add", "--detach", "--quiet", str(hedef))
    return sonuc is not None and sonuc.returncode == 0


def _run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, timeout=60, check=False
        )
    except (OSError, subprocess.SubprocessError):
        # Git yoksa ya da takıldıysa izolasyon kopyayla sürer; iş durmaz.
        return None


def _skipped(relative: Path) -> bool:
    return any(part in _SKIP for part in relative.parts)
