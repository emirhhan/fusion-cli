"""Git çalışma ağacı (worktree) izolasyonu.

Claude Code `--worktree <ad>` ile `.claude/worktrees/<ad>` altında `worktree-<ad>` dalında
çalışır; çıkışta temizse kaldırır, iş kaldıysa korur. Fusion'da karşılığı:

- `fusion --worktree <ad>` / `fusion agent -w <ad>`: oturum `.claude/worktrees/<ad>` kökünde
  (Claude Code ile aynı yer, #337). Eski `.fusion/worktrees/<ad>` ağacı ilk erişimde
  `git worktree move` ile taşınır; künyeler Fusion'a özgüdür, `.fusion/worktrees/.meta`ta kalır.
- REPL `/worktree <ad>` · `/worktree cik` · `/worktree liste`.
- Ajan araçları `enter_worktree` / `exit_worktree` (turdan sonra kök değişir).
- Alt ajan `izolasyon: "worktree"`: üye kendi çalışma ağacında yazar, ana proje değişmez.

Yalnız stdlib: `git` komutları `subprocess` ile çağrılır; çağıran katman gerekirse
`asyncio.to_thread` ile ayırır. Bu modül kullanıcıya metin basmaz, hata `WorktreeError`dır.

Ölçüldü (31 Ekim): depoda `git worktree` kullanımı yoktu; tek izolasyon plan motorunun
dizin kopyasıydı (`core/workspace.py`, `uses_worktree=False`).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .errors import WorktreeError
from .worktree_fetch import BASE_FRESH, BASE_HEAD, fetch_pull_request, fresh_base, quiet_git
from .worktree_pr import parse_pull_request

#: Depo kökü altındaki çalışma ağacı dizini (git'e `info/exclude` ile gizlenir).
WORKTREE_DIR = Path(".claude") / "worktrees"
#: Eski (Fusion'a özgü) çalışma ağacı dizini; künyeler hâlâ burada durur.
LEGACY_WORKTREE_DIR = Path(".fusion") / "worktrees"
#: Oluşturulan dalın öneki: `worktree-<ad>`.
BRANCH_PREFIX = "worktree-"
#: Çalışma ağacına kopyalanacak izlenmeyen dosyaların desen listesi (depo kökünde).
INCLUDE_FILE = ".worktreeinclude"
#: Çalışma ağacı künyelerinin durduğu alt dizin (`.fusion/worktrees/.meta/<ad>.json`;
#: `LEGACY_WORKTREE_DIR` altında).
META_DIR = ".meta"
#: `git` komutu için üst süre (saniye); ağ gerektirmeyen yerel işlemler için bol.
GIT_TIMEOUT_S = 60.0

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


@dataclass(frozen=True, slots=True)
class Worktree:
    """Bir çalışma ağacının künyesi."""

    name: str
    path: Path
    branch: str
    #: Ana depo kökü (çalışma ağacının yaratıldığı yer).
    origin: Path
    #: Dalın ayrıldığı commit; "iş kaldı mı" bununla ölçülür.
    base_commit: str
    #: `.worktreeinclude` ile kopyalanan izlenmeyen dosyalar (ağaca göreli). Bunlar git'te
    #: "yeni dosya" görünür ama kullanıcının İŞİ değildir; temizlik ölçümünde sayılmaz.
    included: tuple[str, ...] = ()


class LeaveOutcome(Enum):
    """Çıkışta çalışma ağacına ne olduğu."""

    REMOVED = "kaldirildi"
    KEPT = "korundu"


@dataclass(frozen=True, slots=True)
class LeaveResult:
    worktree: Worktree
    outcome: LeaveOutcome
    #: Korunduysa neden: "degisiklik" (commit'lenmemiş iş) ya da "commit" (dalda yeni commit).
    reason: str = ""


class WorktreeSwitch:
    """Araçların tur SONUNA bıraktığı kök değişikliği isteği.

    `ToolContext` donmuştur ve kök tur ortasında değişmez; `enter_worktree` isteği
    buraya yazar, REPL turu bitirince kökü değiştirir (bkz. `cli/repl/worktrees`).
    """

    def __init__(self) -> None:
        self.requested: Worktree | None = None
        self.exit_requested = False

    def request(self, worktree: Worktree) -> None:
        self.requested = worktree
        self.exit_requested = False

    def request_exit(self) -> None:
        self.requested = None
        self.exit_requested = True

    def take(self) -> tuple[Worktree | None, bool]:
        """İsteği bir kez al ve temizle."""
        requested, exit_requested = self.requested, self.exit_requested
        self.requested, self.exit_requested = None, False
        return requested, exit_requested


def validate_name(name: str) -> str:
    """Adı doğrula: harf/rakamla başlar; `.`, `_`, `-` dışında ayraç yok; yol parçası olamaz."""
    candidate = name.strip()
    if not _NAME.match(candidate) or candidate in {".", ".."}:
        raise WorktreeError(
            f"Geçersiz çalışma ağacı adı: {name!r}. Harf/rakamla başlayan, en çok 64 "
            "karakterlik bir ad ver (izinli: harf, rakam, nokta, alt çizgi, tire)."
        )
    return candidate


def repository_root(path: Path) -> Path | None:
    """`path` bir git deposundaysa çalışma ağacının kökü; değilse `None`."""
    try:
        output = _git(path, "rev-parse", "--show-toplevel")
    except WorktreeError:
        return None
    return Path(output.strip()).resolve() if output.strip() else None


def project_root_of(path: Path) -> Path:
    """`path` bir Fusion çalışma ağacının içindeyse ana depo kökü; değilse `path` olduğu gibi.

    Yalnız sözcüksel bakar (disk okumaz): `<kök>/.fusion/worktrees/<ad>[/…]` → `<kök>`.
    Sohbet transcript'i buna göre anahtarlanır: çalışma ağacı aynı projenin bir dalıdır,
    konuşma projeye aittir. Ölçüldü (31 Ekim): kök ağaca geçince transcript yeni kök
    digest'i altında ayrı dosyaya gidiyor, masaüstünde geçmiş boşalıyor ve sohbet iki
    dosyaya bölünüyordu.
    """
    for candidate in (path, *path.parents):
        parent = candidate.parent
        if _is_worktrees_dir(parent):
            return parent.parent.parent
    return path


def _is_worktrees_dir(path: Path) -> bool:
    """`<kök>/.claude/worktrees` ya da eski `<kök>/.fusion/worktrees` mi?"""
    return path.name == WORKTREE_DIR.name and path.parent.name in {
        WORKTREE_DIR.parent.name,
        LEGACY_WORKTREE_DIR.parent.name,
    }


def worktree_for_path(path: Path) -> Worktree | None:
    """`path` bir Fusion çalışma ağacının içindeyse künyesi; değilse `None`."""
    resolved = path.expanduser().resolve()
    for candidate in (resolved, *resolved.parents):
        if _is_worktrees_dir(candidate.parent):
            origin = candidate.parent.parent.parent
            return find_worktree(origin, candidate.name)
    return None


def find_worktree(origin: Path, name: str) -> Worktree | None:
    """Künyesi ve dizini duran çalışma ağacını döndür; biri yoksa `None`."""
    meta = _meta_path(origin, name)
    try:
        payload = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    path = _migrated_path(origin, name)
    if not isinstance(payload, dict) or not path.is_dir():
        return None
    included = payload.get("included")
    return Worktree(
        name=name,
        path=path,
        branch=str(payload.get("branch") or f"{BRANCH_PREFIX}{name}"),
        origin=origin,
        base_commit=str(payload.get("base_commit") or ""),
        included=tuple(str(item) for item in included) if isinstance(included, list) else (),
    )


def _migrated_path(origin: Path, name: str) -> Path:
    """Ağacın yeri; eski `.fusion/worktrees/<ad>` varsa `.claude/worktrees/<ad>`'a taşınır.

    Taşıma `git worktree move` ile yapılır (git'in kaydı da güncellenir). Taşınamazsa
    (kilitli ağaç, izin) eski yol olduğu gibi kullanılır: kullanıcının ağacı bozulmaz.
    """
    path = origin / WORKTREE_DIR / name
    legacy = origin / LEGACY_WORKTREE_DIR / name
    if path.is_dir() or not legacy.is_dir():
        return path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _ensure_excluded(origin)
        _git(origin, "worktree", "move", str(legacy), str(path))
    except (OSError, WorktreeError):
        return legacy
    return path


def list_worktrees(origin: Path) -> tuple[Worktree, ...]:
    """Depodaki Fusion çalışma ağaçları, ada göre."""
    meta_dir = origin / LEGACY_WORKTREE_DIR / META_DIR
    try:
        names = sorted(entry.stem for entry in meta_dir.iterdir() if entry.suffix == ".json")
    except FileNotFoundError:
        return ()
    found = (find_worktree(origin, name) for name in names)
    return tuple(worktree for worktree in found if worktree is not None)


def enter_worktree(
    cwd: Path, name: str, *, base_ref: str = "HEAD", base_mode: str = BASE_HEAD
) -> Worktree:
    """Adı verilen çalışma ağacını aç: varsa onu, yoksa `base_ref`'ten yenisini.

    `cwd` bir çalışma ağacının içindeyse ana depoya gidilir; iç içe ağaç açılmaz. `base_ref`
    `cwd`'nin KENDİ checkout'unda çözülür: bir ağaçtan açılan yeni ağaç (alt ajan izolasyonu)
    o ağacın dalından dallanır. Ölçüldü (31 Ekim): ana depoda çözülünce üye, oturumun
    dalındaki işi görmeyen ana HEAD'in kopyasında çalışıyordu.

    `base_mode` Claude Code `worktree.baseRef`'idir (#338): `"head"` yukarıdaki davranış,
    `"fresh"` uzak varsayılan dal (`origin/HEAD`; yoksa yerel `HEAD`). Varsayılanı çağıran
    ayardan verir (`config.worktree_settings`); burada geri uyum için `"head"`.
    """
    pull_request = parse_pull_request(name)
    name = validate_name(pull_request.worktree_name if pull_request else name)
    inside = worktree_for_path(cwd)
    origin = inside.origin if inside is not None else repository_root(cwd)
    if origin is None:
        raise WorktreeError(
            f"Burası bir git deposu değil: {cwd}. Çalışma ağacı için önce `git init` gerekir."
        )
    existing = find_worktree(origin, name)
    if existing is not None:
        return existing
    if pull_request is not None:
        # PR/MR başı `origin`'den çekilir (Claude Code, #341); taban FETCH_HEAD'dir.
        remote = quiet_git(origin, ("remote", "get-url", "origin"), timeout_s=GIT_TIMEOUT_S) or ""
        fetch_pull_request(origin, pull_request.refspecs(remote), pull_request.number)
        cwd, base_ref = origin, "FETCH_HEAD"
    elif base_mode == BASE_FRESH and (fresh := fresh_base(origin)) != "HEAD":
        cwd, base_ref = origin, fresh  # yedek `HEAD` bulunulan checkout'ta çözülür
    base_commit = _git(cwd, "rev-parse", "--verify", f"{base_ref}^{{commit}}").strip()
    return create_worktree(origin, name, base_ref=base_commit)


def create_worktree(origin: Path, name: str, *, base_ref: str = "HEAD") -> Worktree:
    """`origin/.claude/worktrees/<ad>` altında `worktree-<ad>` dalıyla yeni ağaç kur."""
    name = validate_name(name)
    origin = origin.expanduser().resolve()
    path = origin / WORKTREE_DIR / name
    if path.exists():
        raise WorktreeError(
            f"Bu adda bir dizin zaten var ama künyesi yok: {path}. "
            "Dizini kaldır ya da başka ad ver."
        )
    branch = f"{BRANCH_PREFIX}{name}"
    base_commit = _git(origin, "rev-parse", "--verify", f"{base_ref}^{{commit}}").strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    _ensure_excluded(origin)
    if _branch_exists(origin, branch):
        _git(origin, "worktree", "add", str(path), branch)
    else:
        _git(origin, "worktree", "add", "-b", branch, str(path), base_commit)
    copied = copy_includes(origin, path)
    worktree = Worktree(
        name=name,
        path=path,
        branch=branch,
        origin=origin,
        base_commit=base_commit,
        included=tuple(item.as_posix() for item in copied),
    )
    _write_meta(worktree)
    return worktree


def copy_includes(origin: Path, target: Path) -> tuple[Path, ...]:
    """`.worktreeinclude` desenlerine uyan, hedefte OLMAYAN dosyaları kopyala (`.env` gibi).

    Desenler depo köküne göre glob'dur; `.git` ve `.fusion` altı asla kopyalanmaz.
    Kopyalanan yolları (hedefe göreli) döndürür.

    Dosya depoyla gelir, yani güvenilmez. Ölçüldü (31 Ekim): `../x` deseni ve depo dışına
    işaret eden symlink depo DIŞINDAN okunup ağaca (ya da ağacın dışına) yazılıyordu;
    `restrict_to_root`'un koruduğu sırlar böylece ajanın köküne taşınırdı. Bu yüzden `..`
    ve mutlak desen reddedilir, symlink'ler atlanır, kaynak da hedef de kendi kökünün içinde
    kalmak zorundadır.
    """
    include = origin / INCLUDE_FILE
    try:
        patterns = [
            line.strip()
            for line in include.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    except OSError:
        return ()
    origin_real = origin.resolve()
    target_real = target.resolve()
    copied: list[Path] = []
    for pattern in patterns:
        if not _is_safe_include_pattern(pattern):
            continue
        for source in sorted(origin.glob(pattern)):
            relative = source.relative_to(origin)
            if relative.parts[0] in {".git", ".fusion"} or relative.parts[:2] == WORKTREE_DIR.parts:
                continue
            if not _is_inside(source, origin_real) or not source.is_file():
                continue
            destination = target / relative
            if not _is_inside(destination, target_real, must_exist=False) or destination.exists():
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied.append(relative)
    return tuple(copied)


def _is_safe_include_pattern(pattern: str) -> bool:
    """Desen depo kökünün içinde kalır mı? `..` parçası ve mutlak yol dışarı çıkabilir."""
    parts = Path(pattern).parts
    return bool(parts) and not Path(pattern).is_absolute() and ".." not in parts


def _is_inside(path: Path, root_real: Path, *, must_exist: bool = True) -> bool:
    """`path` (= kök / göreli), symlink izlemeden ve çözüldükten sonra `root_real` altında mı?

    Göreli yolun hiçbir parçası symlink olamaz: `disa-dizin/x` symlink dizin üzerinden depo
    dışına çıkar; `resolve()` tek başına bunu yakalar ama depo İÇİNE işaret eden link de
    kopyalanmamalı (git onu dosya değil link olarak taşır). Kökün kendisi symlink'li bir
    yoldan verilmiş olabilir (macOS `/tmp`); o yüzden yalnız kökten SONRAKİ parçalar sınanır.
    """
    try:
        resolved = path.resolve(strict=must_exist)
    except OSError:
        return False
    if resolved != root_real and root_real not in resolved.parents:
        return False
    try:
        relative = resolved.relative_to(root_real)
    except ValueError:
        return False
    probe = path.parent
    for _ in relative.parts:
        if probe.is_symlink():
            return False
        probe = probe.parent
    return not path.is_symlink()


def is_dirty(worktree: Worktree) -> bool:
    """Commit'lenmemiş (değişmiş ya da izlenmeyen) dosya var mı?

    `.worktreeinclude` ile kopyalanan dosyalar sayılmaz: onlar iş değil, ayar kopyasıdır.
    """
    output = _git(worktree.path, "status", "--porcelain", "--untracked-files=all")
    for line in output.splitlines():
        if len(line) < 4:
            continue
        changed_path = line[3:].strip().strip('"')
        if line.startswith("??") and changed_path in worktree.included:
            continue
        return True
    return False


def has_new_commits(worktree: Worktree) -> bool:
    """Dal, ayrıldığı commit'in ötesine geçti mi?"""
    if not worktree.base_commit:
        return False
    output = _git(worktree.path, "rev-list", "--count", f"{worktree.base_commit}..HEAD")
    return int(output.strip() or "0") > 0


def leave_worktree(worktree: Worktree) -> LeaveResult:
    """Çıkış kuralı: temiz ve commit'siz ağaç kaldırılır, iş kalmışsa korunur."""
    if is_dirty(worktree):
        return LeaveResult(worktree, LeaveOutcome.KEPT, "degisiklik")
    if has_new_commits(worktree):
        return LeaveResult(worktree, LeaveOutcome.KEPT, "commit")
    # Temizlik yukarıda KENDİ ölçümümüzle kanıtlandı; `--force` yalnız `.worktreeinclude`
    # kopyalarının (git'e göre izlenmeyen dosya) kaldırmayı engellememesi için.
    remove_worktree(worktree, force=bool(worktree.included))
    return LeaveResult(worktree, LeaveOutcome.REMOVED)


def remove_worktree(worktree: Worktree, *, force: bool = False) -> None:
    """Ağacı ve (commit'siz kaldıysa) dalını kaldır; künyeyi sil."""
    args = ["worktree", "remove", *(["--force"] if force else []), str(worktree.path)]
    _git(worktree.origin, *args)
    if not has_new_commits_on_branch(worktree):
        _git(worktree.origin, "branch", "-D", worktree.branch)
    _meta_path(worktree.origin, worktree.name).unlink(missing_ok=True)


def has_new_commits_on_branch(worktree: Worktree) -> bool:
    """Ağaç kaldırıldıktan sonra dalın yeni commit taşıyıp taşımadığı (ana depodan ölçülür)."""
    if not worktree.base_commit or not _branch_exists(worktree.origin, worktree.branch):
        return False
    output = _git(
        worktree.origin, "rev-list", "--count", f"{worktree.base_commit}..{worktree.branch}"
    )
    return int(output.strip() or "0") > 0


def _branch_exists(origin: Path, branch: str) -> bool:
    try:
        _git(origin, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")
    except WorktreeError:
        return False
    return True


#: `info/exclude` satırları: Fusion durumu ve Claude Code çalışma ağaçları git'te görünmez.
_EXCLUDED = (".fusion/", f"{WORKTREE_DIR.as_posix()}/")


def _ensure_excluded(origin: Path) -> None:
    """`.fusion/` ve `.claude/worktrees/` git durumunda görünmesin (`info/exclude`, bir kez)."""
    try:
        git_dir = Path(_git(origin, "rev-parse", "--git-common-dir").strip())
        if not git_dir.is_absolute():
            git_dir = origin / git_dir
        exclude = git_dir / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        current = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
        missing = [line for line in _EXCLUDED if line not in current.splitlines()]
        if missing:
            with exclude.open("a", encoding="utf-8") as stream:
                lead = "" if current.endswith("\n") or not current else "\n"
                stream.write(lead + "".join(f"{line}\n" for line in missing))
    except (OSError, WorktreeError):
        # Dışlama bir kolaylıktır, ön koşul değil: yazılamazsa `.fusion/` git durumunda görünür.
        return


def _meta_path(origin: Path, name: str) -> Path:
    return origin / LEGACY_WORKTREE_DIR / META_DIR / f"{name}.json"


def _write_meta(worktree: Worktree) -> None:
    meta = _meta_path(worktree.origin, worktree.name)
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text(
        json.dumps(
            {
                "name": worktree.name,
                "branch": worktree.branch,
                "base_commit": worktree.base_commit,
                "included": list(worktree.included),
                "created_at": time.time(),
            }
        ),
        encoding="utf-8",
    )


def _git(cwd: Path, *args: str) -> str:
    """`git` çalıştır, stdout döndür; başarısızlık `WorktreeError` (stderr özetiyle)."""
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_S,
            check=False,
        )
    except FileNotFoundError as error:
        raise WorktreeError("`git` bulunamadı; çalışma ağacı için git kurulu olmalı.") from error
    except (OSError, subprocess.TimeoutExpired) as error:
        raise WorktreeError(f"git çalıştırılamadı ({type(error).__name__}).") from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        summary = detail[-1] if detail else f"çıkış kodu {completed.returncode}"
        raise WorktreeError(f"git {args[0]} başarısız: {summary}")
    return completed.stdout
