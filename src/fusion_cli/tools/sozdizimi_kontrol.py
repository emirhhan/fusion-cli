"""Düzenleme sonrası hızlı sözdizimi kontrolü (`runtime.post_edit_syntax_check`).

SWE-agent'ın ACI dersi: düzenleme anında çalışan bir denetim, bozuk sözdizimini aynı turda
modele geri verir; yoksa hata ancak sonraki çalıştırmada, birkaç tur sonra görülür.

Bu kontrol UYARIDIR, engel değildir: dosya zaten yazılmıştır ve geri alınmaz (parça parça
yazan akışlar geçici olarak geçersiz kod bırakabilir). Python burada YOKTUR: `.py`
sözdizimi zaten yazmadan ÖNCE `core.structured_files.validate_structured` ile engellenir.

Denetleyici kuruluysa çalışır, yoksa sessizce atlanır:

- `.js/.mjs/.cjs`: `node --check` (kod ÇALIŞTIRILMAZ, yalnız ayrıştırılır). `.js` dosyası ESM
  sözdizimi taşıyorsa eski Node'lar reddeder; o durumda geçici `.mjs` kopyasıyla yeniden denenir.
  JSX içeren `.js` atlanır (düz Node JSX'i ayrıştıramaz, yanlış alarm olurdu).
- `.ts/.tsx/.mts/.cts`: yalnız `tsc` KURULUYSA (PATH ya da yukarı doğru `node_modules/.bin`);
  tür hataları (TS2xxx) yok sayılır, yalnız sözdizimi (TS1xxx) bildirilir. `npx` ile ağdan
  indirme YAPILMAZ.
- `.php`: `php -l`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path

from ..core.tools import ToolContext
from .wordpress_setup import tool_path

#: Denetleyici için zaman aşımı (sn). Aşılırsa kontrol sessizce atlanır; düzenlemeyi geciktirmez.
SYNTAX_CHECK_TIMEOUT_S = 8.0

#: Modele dönen sorun satırının öneki (testler ve model için sabit).
SYNTAX_ERROR_PREFIX = "sözdizimi hatası"

#: Bir hata mesajının uzunluk tavanı (karakter).
_MAX_MESSAGE_CHARS = 200

_NODE_EXTENSIONS = frozenset({".js", ".mjs", ".cjs"})
_TS_EXTENSIONS = frozenset({".ts", ".tsx", ".mts", ".cts"})

#: Düz Node'un ayrıştıramayacağı JSX işaretleri: React içe aktarımı ya da dönüş/ok-işlevi
#: gövdesinde açılan etiket.
_JSX_HINT = re.compile(
    r"""from\s+['"]react['"]|require\(\s*['"]react['"]\s*\)|"""
    r"""(?:return|=>)\s*\(?\s*<[A-Za-z]|<[A-Z][\w.]*(?:\s[^<>]*)?/?>"""
)
#: ESM sözdizimi eski bir Node'da CommonJS olarak okununca çıkan mesajlar.
_ESM_HINT = re.compile(
    r"Cannot use import statement outside a module|Unexpected token 'export'|"
    r"Cannot use 'import\.meta' outside a module"
)
_NODE_LOCATION = re.compile(r"^.*:(\d+)\s*$")
_PHP_LINE = re.compile(r"^(?:PHP )?Parse error:\s*(.*?) in .+? on line (\d+)\s*$", re.M)
_TSC_LINE = re.compile(r"\((\d+),\d+\): error TS1\d{3}: (.*)$", re.M)

Checker = Callable[[Path, Path, Mapping[str, str]], str | None]


def _problem(line: int, message: str) -> str:
    return f"{SYNTAX_ERROR_PREFIX}: satır {line}: {message.strip()[:_MAX_MESSAGE_CHARS]}"


def _run(command: list[str], env: Mapping[str, str]) -> subprocess.CompletedProcess[str] | None:
    """Denetleyiciyi çalıştır; zaman aşımı/başlatılamama durumunda `None` (sessiz atla)."""
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=SYNTAX_CHECK_TIMEOUT_S,
            env=dict(env),
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None


def _parse_node(stderr: str) -> str | None:
    """`node --check` çıktısından "satır N: mesaj" üret."""
    lines = [line for line in stderr.splitlines() if line.strip()]
    if not lines:
        return None
    location = _NODE_LOCATION.match(lines[0])
    message = next((line for line in lines if re.match(r"\w*Error: ", line)), "")
    if location is None or not message:
        return None
    return _problem(int(location.group(1)), message.split(": ", 1)[1])


def _node_check(path: Path, _root: Path, env: Mapping[str, str]) -> str | None:
    node = shutil.which("node", path=env.get("PATH"))
    if node is None:
        return None
    if path.suffix == ".js" and _JSX_HINT.search(_read(path)):
        return None
    result = _run([node, "--check", str(path)], env)
    if result is None or result.returncode == 0:
        return None
    if path.suffix == ".js" and _ESM_HINT.search(result.stderr):
        return _node_check_as_module(node, path, env)
    return _parse_node(result.stderr)


def _node_check_as_module(node: str, path: Path, env: Mapping[str, str]) -> str | None:
    """ESM sözdizimli `.js`'i geçici `.mjs` kopyasıyla denetle."""
    with tempfile.TemporaryDirectory(prefix="fusion-sozdizimi-") as folder:
        copy = Path(folder) / "kontrol.mjs"
        try:
            copy.write_text(_read(path), encoding="utf-8")
        except OSError:
            return None
        result = _run([node, "--check", str(copy)], env)
    if result is None or result.returncode == 0:
        return None
    return _parse_node(result.stderr)


def _php_check(path: Path, _root: Path, env: Mapping[str, str]) -> str | None:
    php = shutil.which("php", path=env.get("PATH"))
    if php is None:
        return None
    result = _run([php, "-l", str(path)], env)
    if result is None or result.returncode == 0:
        return None
    match = _PHP_LINE.search(result.stdout + "\n" + result.stderr)
    if match is None:
        return None
    return _problem(int(match.group(2)), match.group(1))


def _find_tsc(path: Path, root: Path, env: Mapping[str, str]) -> str | None:
    """Kurulu `tsc`: dosyadan köke doğru `node_modules/.bin/tsc`, sonra PATH."""
    resolved_root = root.resolve()
    for folder in (path.resolve().parent, *path.resolve().parents):
        candidate = folder / "node_modules" / ".bin" / "tsc"
        if candidate.is_file():
            return str(candidate)
        if folder == resolved_root:
            break
    return shutil.which("tsc", path=env.get("PATH"))


def _parse_tsc(output: str) -> str | None:
    """`tsc` çıktısında YALNIZ sözdizimi (TS1xxx) hatalarını al; ilkini bildir."""
    match = _TSC_LINE.search(output)
    return None if match is None else _problem(int(match.group(1)), match.group(2))


def _ts_check(path: Path, root: Path, env: Mapping[str, str]) -> str | None:
    tsc = _find_tsc(path, root, env)
    if tsc is None:
        return None
    command = [
        tsc,
        "--noEmit",
        "--noResolve",
        "--skipLibCheck",
        "--types",
        "",
        "--target",
        "esnext",
        "--module",
        "esnext",
        "--jsx",
        "preserve",
        str(path),
    ]
    result = _run(command, env)
    if result is None or result.returncode == 0:
        return None
    return _parse_tsc(result.stdout + "\n" + result.stderr)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _checker_for(suffix: str) -> Checker | None:
    if suffix in _NODE_EXTENSIONS:
        return _node_check
    if suffix in _TS_EXTENSIONS:
        return _ts_check
    if suffix == ".php":
        return _php_check
    return None


def syntax_problem(path: Path, root: Path, env: Mapping[str, str]) -> str | None:
    """Yazılmış dosyanın sözdizimi sorunu ("sözdizimi hatası: satır N: ..."); yoksa `None`.

    Kontrol edilemeyen her durum (denetleyici yok, zaman aşımı, tanınmayan çıktı) `None`
    döner: yanlış alarm, kaçırılan hatadan daha pahalıdır.
    """
    checker = _checker_for(path.suffix.casefold())
    if checker is None:
        return None
    return checker(path, root, env)


def _check_env(hidden: frozenset[str]) -> dict[str, str]:
    """Denetleyici ortamı: Homebrew'lu PATH, MCP sırları çıkarılmış."""
    env = {name: value for name, value in os.environ.items() if name not in hidden}
    env["PATH"] = tool_path()
    return env


def syntax_note(path: Path, context: ToolContext) -> str:
    """Araç sonucuna eklenecek sözdizimi uyarısı (önünde satır sonu); yoksa boş metin.

    Ayar kapalıysa ya da sorun yoksa boş döner. Dosya zaten yazılmıştır; bu yalnız bildirimdir.
    """
    if not context.post_edit_syntax_check:
        return ""
    problem = syntax_problem(path, context.root, _check_env(context.hidden_env))
    return f"\n{problem}" if problem else ""
