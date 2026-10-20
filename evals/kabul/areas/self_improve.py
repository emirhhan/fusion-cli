"""Kabul alanı: Fusion kendi deposunun kopyasında küçük bir özellik ekler.

Ajan, bu deponun `git worktree` kopyasında çalışır (çalışma kökü `root_key="repo"`
ile kopyanın kendisidir). Ölçüm ajandan BAĞIMSIZdır: gizli testler kopyanın dışında
durur, yalnız denetim sırasında ve kopyanın `src`'si öncelikli olacak biçimde
çalıştırılır; böylece ajan testleri görüp onlara göre kod uyduramaz.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from evals.kabul.model import Area, Check, Inspection
from fusion_cli.core.errors import FusionError

#: Worktree'nin kopyalanacağı alt klasör (çalışma klasörü içinde).
REPO_DIRNAME = "fusion-cli"
#: Görev metni ve `Area.root_key` ile eşleşen değer anahtarı.
REPO_KEY = "repo"
#: Gizli testler: bu modülün yanında, ajanın kopyasının DIŞINDA durur.
HIDDEN_TEST = Path(__file__).resolve().parent / "self_improve_hidden" / "test_mcp_add_url.py"
#: Mevcut yapılandırma yazıcısı testleri (gerileme denetimi).
WRITER_TESTS = "tests/test_config_writer.py"
#: Tek bir denetim komutunun üst süresi (saniye); mypy soğuk çalışmada yavaştır.
COMMAND_TIMEOUT_S = 900.0
#: Ajanın dokunmaması gereken yol önekleri (kopya köküne göreli).
FORBIDDEN_PREFIXES = ("evals/",)
#: Denetçi alt süreçlerine geçirilen asgari ortam; kullanıcı yapılandırması sızmaz.
_PASSTHROUGH_ENV = ("PATH", "LANG", "LC_ALL")

TASK = (
    "Çalışma klasörün Fusion deposunun bir kopyasıdır. `fusion mcp-add` komutu bugün "
    "yalnız stdio sunucu ekliyor (`src/fusion_cli/cli/app.py` içindeki mcp_add). "
    "Uzak (streamable_http) sunucu eklemek için `--url` ve Bearer token'ın ORTAM "
    "DEĞİŞKENİ adını alan `--token-env` seçenekleri ekle. `--url` verildiğinde "
    "`command` argümanı verilmeyebilir ve transport `streamable_http` olur. İkisi "
    "birlikte (command + --url) verilirse anlaşılır Türkçe hata ver ve çıkış kodu "
    "sıfırdan farklı olsun; hiçbiri yoksa da hata ver. Token'ın kendisi değil yalnız "
    "ortam değişkeninin adı yapılandırmaya yazılır. Proje kurallarına (RULES.md) uy, "
    "test yaz, `ruff` ve `mypy` temiz olsun."
)


class WorktreeError(FusionError):
    """Kopya (git worktree) oluşturulamadı."""


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Denetim alt sürecinin sonucu."""

    returncode: int
    output: str


def _run(command: list[str], cwd: Path, env: Mapping[str, str] | None = None) -> CommandResult:
    """Komutu zaman aşımıyla çalıştır; çalışamazsa 127 döner (çıktıda neden yazar)."""
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=None if env is None else dict(env),
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CommandResult(127, f"komut çalışamadı: {exc}")
    return CommandResult(completed.returncode, (completed.stdout + completed.stderr).strip())


def _source_repo() -> Path:
    """Bu deponun kökü; modül konumundan bulunur."""
    here = Path(__file__).resolve().parent
    result = _run(["git", "-C", str(here), "rev-parse", "--show-toplevel"], here)
    if result.returncode != 0:
        raise WorktreeError(f"depo kökü bulunamadı: {result.output}")
    return Path(result.output.splitlines()[-1])


@contextmanager
def prepare(workdir: Path) -> Iterator[Mapping[str, str]]:
    """Depodan ayrık (detached) bir worktree aç; çıkışta kaldır."""
    source = _source_repo()
    target = workdir / REPO_DIRNAME
    added = _run(
        ["git", "-C", str(source), "worktree", "add", "--detach", str(target), "HEAD"], source
    )
    if added.returncode != 0:
        raise WorktreeError(f"worktree açılamadı: {added.output}")
    try:
        yield {REPO_KEY: str(target)}
    finally:
        _save_diff(target, workdir / DIFF_NAME)
        _run(["git", "-C", str(source), "worktree", "remove", "--force", str(target)], source)
        _run(["git", "-C", str(source), "worktree", "prune"], source)


#: Worktree silinmeden önce Fusion'ın değişikliğinin kaydedildiği dosya. Kullanıcı
#: (6 Ekim 2026): "geçti" denen işi kendi gözüyle görmek istedi; worktree koşu
#: sonunda siliniyordu ve geriye yalnız olay kaydı kalıyordu.
DIFF_NAME = "fusion-degisikligi.diff"


def _save_diff(repo: Path, out: Path) -> None:
    """Yeni dosyalar dahil tüm değişikliği tek bir diff dosyasına yaz (hata turu düşürmez)."""
    _run(["git", "-C", str(repo), "add", "--intent-to-add", "--all"], repo)
    fark = _run(["git", "-C", str(repo), "diff", "HEAD"], repo)
    with contextlib.suppress(OSError):
        out.write_text(fark.output, encoding="utf-8")


def _inspection_env(repo: Path, scratch: Path) -> dict[str, str]:
    """Kopyanın `src`'si öncelikli, kullanıcı dizinleri geçici klasöre alınmış ortam."""
    env = {key: os.environ[key] for key in _PASSTHROUGH_ENV if key in os.environ}
    env.update(
        PYTHONPATH=str(repo / "src"),
        HOME=str(scratch),
        XDG_CONFIG_HOME=str(scratch / "config"),
        XDG_DATA_HOME=str(scratch / "data"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    return env


def _check_from(name: str, result: CommandResult) -> Check:
    """Komut sonucunu maddeye çevir: sıfır çıkış kodu geçer, çıktı sonu ayrıntı olur."""
    return Check(name, result.returncode == 0, result.output[-400:])


def _pytest(repo: Path, env: Mapping[str, str], target: str) -> CommandResult:
    command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", target]
    return _run(command, repo, env)


def _changed_paths(repo: Path) -> tuple[str, ...] | None:
    """`git status --porcelain` çıktısındaki yollar; git çalışmazsa None."""
    result = _run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"], repo)
    if result.returncode != 0:
        return None
    return tuple(line[3:].strip() for line in result.output.splitlines() if line.strip())


def _git_checks(repo: Path) -> tuple[Check, ...]:
    paths = _changed_paths(repo)
    if paths is None:
        return ()
    touched = tuple(path for path in paths if path.startswith(FORBIDDEN_PREFIXES))
    added_tests = tuple(path for path in paths if path.startswith("tests/"))
    return (
        Check("test_eklendi", bool(added_tests), ", ".join(added_tests)),
        Check("yasak_yola_dokunulmadi", not touched, ", ".join(touched)),
    )


def inspect(workdir: Path, values: Mapping[str, str]) -> Inspection:
    """Ajanın kopyasını bağımsız ölç: gizli testler, ruff, mypy, gerileme, git."""
    if REPO_KEY not in values:
        return Inspection(invalid_reason="değerlerde kopya yolu yok")
    repo = Path(values[REPO_KEY])
    if not repo.is_dir() or not HIDDEN_TEST.is_file():
        return Inspection(invalid_reason="kopya ya da gizli test bulunamadı")
    scratch = workdir / ".kabul_denetim"
    scratch.mkdir(parents=True, exist_ok=True)
    env = _inspection_env(repo, scratch)
    git_checks = _git_checks(repo)
    if not git_checks:
        return Inspection(invalid_reason="git durumu okunamadı")
    ruff = _run(
        [sys.executable, "-m", "ruff", "check", "--no-cache", "src/fusion_cli/cli"], repo, env
    )
    mypy = _run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--cache-dir",
            str(scratch / "mypy"),
            "src/fusion_cli/cli/app.py",
        ],
        repo,
        env,
    )
    checks = (
        _check_from("gizli_testler_gecti", _pytest(repo, env, str(HIDDEN_TEST))),
        _check_from("ruff_temiz", ruff),
        _check_from("mypy_temiz", mypy),
        *git_checks,
        _check_from("config_writer_testleri_gecti", _pytest(repo, env, WRITER_TESTS)),
    )
    return Inspection(checks=checks)


AREA = Area(
    name="kendini_gelistirme",
    task=TASK,
    timeout_s=3600.0,
    inspect=inspect,
    prepare=prepare,
    root_key=REPO_KEY,
)
