"""Koşu içinde araç üretimi — ajan kendine görev-özel araç yazar.

Live-SWE-agent'ın ölçümü: yalnız bash ile başlayıp koşu sırasında kendine Python
araçları yazan ajan SWE-bench Verified'da %77,4 aldı, çevrimdışı eğitim maliyeti
sıfır. Kazancın kaynağı basit: tekrar eden mekanik işi (aynı dizini süzmek, aynı
biçimi ayrıştırmak, aynı raporu çıkarmak) bir kez yazıp sonraki adımlarda ÇAĞIRMAK.

Bu bir KUM HAVUZU DEĞİLDİR. Araç, Fusion süreci içinde `exec` ile çalışır; aşağıdakiler
kazara zararı azaltan KATMANLARDIR, kararlı bir saldırgana karşı yalıtım değil (T1-09):

- Kaynak diske yazılmadan ÖNCE `compile` ile denetlenir; bozuk kod kaydedilmez.
- Araç `.fusion/tools/<ad>.py` altında durur ve adı yol kaçışı içeremez.
- AST denetimi silme/taşıma, süreç başlatma, ağ, dinamik içe aktarma, ortam değişkeni ve
  dunder zinciri (`__subclasses__`) kullanımını NİTELİKLİ adla reddeder (`os.remove`
  reddedilir, `"a".replace(...)` ve `lst.remove(x)` reddedilmez).
- `path`/`yol` argümanları ve aracın kendi `open()` çağrıları kök kuralından
  (`resolve_path`/`writable_path`) geçer. `pathlib` ile doğrudan G/Ç (`Path.write_text`)
  bu denetimin DIŞINDADIR: gerçek yalıtım için ayrı süreç gerekir (yapılmadı).
- Aile `EXTERNAL`, araç `mutating`'dir: adım kapsamı ve onay kuralları aynen geçerlidir.
- Yalnız Fusion'ın yazdığı (veya kullanıcının `fusion trust` ile onayladığı) içerik
  yüklenir ve çalıştırılır. İndirilmiş bir depodaki `.fusion/tools/*.py` ya da
  üretildikten sonra değiştirilmiş araç çalışmaz (bkz. `config/trust.py`).
- Silme ve komut işi `run_shell`'den yapılır: orada yıkıcı desen denetimi ve çöp
  koruması vardır (1 Ekim 2026: üretilen araçlar bu yoldan geçmiyordu).
"""

from __future__ import annotations

import ast
import builtins
import os
import re
from pathlib import Path
from typing import IO, Any

from ..config import trust
from ..core.constants import MAX_OUTPUT_CHARS
from ..core.tools import Tool, ToolArgs, ToolContext, ToolResult
from .args import require_str
from .files import resolve_path, writable_path

#: Üretilen araçların yaşadığı dizin (proje kökü altında).
FORGE_DIR = ".fusion/tools"
_SAFE_NAME = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


def forge_tool(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Yeni bir araç yaz ve kaydet."""
    name = require_str(args, "name")
    source = require_str(args, "source")
    if not _SAFE_NAME.match(name):
        return ToolResult.failure(
            f"Geçersiz araç adı: {name}. Yalnız küçük harf, rakam ve alt çizgi kullan."
        )
    hata = _validate(source)
    if hata is not None:
        return ToolResult.failure(hata)
    if name in _builtin_names(context):
        # `load_forged_tools` çakışan adı zaten atlar (yerleşik araç korunur); ama
        # sessizce "araç üretildi" demek modeli yanıltıp var olmayan aracı bekletirdi.
        return ToolResult.failure(
            f"'{name}' bir yerleşik araç adı; farklı bir ad seç (ör. {name}_ozel)."
        )
    hedef = context.root / FORGE_DIR / f"{name}.py"
    if hedef.is_symlink() or hedef.parent.is_symlink():
        # Bağın arkasına yazmak araç dosyasını proje kökü dışına koyardı.
        return ToolResult.failure(f"Araç yolu sembolik bağ: {hedef}. Başka bir ad seç.")
    hedef.parent.mkdir(parents=True, exist_ok=True)
    # Geri alma kaydı YAZMADAN ÖNCE (diğer dosya araçlarıyla aynı sıra): var olan aracı
    # ezince eski içerik ancak böyle geri gelir.
    context.changes.record(hedef)
    hedef.write_text(source, encoding="utf-8")
    trust.approve_file(context.root, hedef)
    return ToolResult(f"araç üretildi: {name} ({hedef}). Sonraki adımlarda çağırabilirsin.")


def _builtin_names(context: ToolContext) -> frozenset[str]:
    """Yerleşik + bu oturumda sunulan araç adları (üretilen araç bunlarla çakışamaz)."""
    from . import build_registry  # tembel: `tools/__init__` bu modülü içe aktarır

    return frozenset(build_registry().names()) | frozenset(context.available_tools)


def load_forged_tools(root: Path) -> tuple[Tool, ...]:
    """Üretilmiş araçları kayıt defterine hazır hâlde döndür."""
    dizin = root / FORGE_DIR
    if not dizin.is_dir():
        return ()
    return tuple(
        _build(path)
        for path in sorted(dizin.glob("*.py"))
        if _SAFE_NAME.match(path.stem)
        and trust.is_file_trusted(root, path)
        and _validate(_read(path)) is None
    )


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


#: Üretilen araçta yasak modüller: süreç, ağ, dinamik kod ve serileştirme (kod çalıştırır).
_FORBIDDEN_MODULES = frozenset(
    {
        "subprocess", "shutil", "ctypes", "multiprocessing", "pty", "socket", "ssl", "urllib",
        "http", "ftplib", "smtplib", "telnetlib", "poplib", "imaplib", "xmlrpc", "socketserver",
        "requests", "httpx", "aiohttp", "webbrowser", "importlib", "runpy", "imp", "code",
        "codeop", "pickle", "marshal", "builtins",
    }
)  # fmt: skip
#: `os` modülünde yasak üyeler (silme, taşıma, süreç, ortam, yetki). Ek olarak
#: `exec*`, `spawn*` ve `posix_spawn*` aileleri.
_OS_MODULES = frozenset({"os", "posix", "nt"})
_OS_FORBIDDEN = frozenset(
    {
        "remove", "unlink", "rmdir", "removedirs", "rename", "renames", "replace", "system",
        "popen", "kill", "killpg", "truncate", "ftruncate", "fork", "forkpty", "startfile",
        "environ", "environb", "getenv", "putenv", "unsetenv", "chmod", "chown", "symlink",
        "link",
    }
)  # fmt: skip
_OS_FORBIDDEN_PREFIXES = ("exec", "spawn", "posix_spawn")
#: Her gövdeden yasak çağrı adları: yalnız bu ada SAHİP olabilecek Path/asyncio metotları
#: (`str.rename` yoktur) ve yerleşikler.
_FORBIDDEN_METHODS = frozenset(
    {"rmtree", "unlink", "rmdir", "rename", "create_subprocess_exec", "create_subprocess_shell"}
)
_FORBIDDEN_BUILTINS = frozenset(
    {"exec", "eval", "compile", "__import__", "getattr", "globals", "locals", "breakpoint"}
)
#: Sınıf zincirinden kısıtlı kapsamdan kaçış (`().__class__.__bases__[0].__subclasses__()`).
_ESCAPE_ATTRIBUTES = frozenset(
    {
        "__bases__", "__base__", "__subclasses__", "__globals__", "__builtins__", "__mro__",
        "__code__", "__closure__", "__getattribute__", "__reduce__", "__reduce_ex__",
    }
)  # fmt: skip


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    """`import os as o` → {"o": "os"}; `from os import remove as r` → {"r": "os.remove"}."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split(".")[0]] = alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return aliases


def _os_member_forbidden(member: str) -> bool:
    return member in _OS_FORBIDDEN or member.startswith(_OS_FORBIDDEN_PREFIXES)


def _forbidden_import(node: ast.AST) -> str | None:
    if isinstance(node, ast.Import):
        names = [alias.name for alias in node.names]
    elif isinstance(node, ast.ImportFrom):
        names = [node.module or ""]
        if (node.module or "").split(".")[0] in _OS_MODULES:
            for alias in node.names:
                if _os_member_forbidden(alias.name):
                    return f"`{node.module}.{alias.name}`"
    else:
        return None
    for name in names:
        if name.split(".")[0] in _FORBIDDEN_MODULES:
            return f"`{name}` modülü"
    return None


def _forbidden_attribute(node: ast.Attribute, aliases: dict[str, str]) -> str | None:
    base = node.value.id if isinstance(node.value, ast.Name) else ""
    module = aliases.get(base, "")
    if module in _OS_MODULES and _os_member_forbidden(node.attr):
        return f"`{module}.{node.attr}`"
    if module == "sys" and node.attr == "modules":
        return "`sys.modules`"
    if node.attr in _ESCAPE_ATTRIBUTES:
        return f"`.{node.attr}` (kısıtlı kapsamdan kaçış)"
    return None


def _forbidden_call(node: ast.Call) -> str | None:
    callee = node.func
    if isinstance(callee, ast.Name) and callee.id in _FORBIDDEN_BUILTINS:
        return f"`{callee.id}(...)` çağrısı"
    if not isinstance(callee, ast.Attribute):
        return None
    if callee.attr in _FORBIDDEN_METHODS:
        return f"`.{callee.attr}(...)` çağrısı"
    # `Path.replace(hedef)` tek argümanlıdır; `str.replace(a, b)` iki argümanlıdır.
    one_argument = len(node.args) == 1 or any(isinstance(a, ast.Starred) for a in node.args)
    if callee.attr == "replace" and one_argument:
        return "`.replace(hedef)` çağrısı (Path.replace dosyanın üzerine yazar)"
    return None


def _forbidden_use(tree: ast.AST) -> str | None:
    """Yasak kullanımı NİTELİKLİ adla bul: `os.remove` yasak, `"a".replace(...)` serbest."""
    aliases = _import_aliases(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in {"__builtins__", "__import__"}:
            return f"`{node.id}`"
        found = (
            _forbidden_import(node)
            or (_forbidden_attribute(node, aliases) if isinstance(node, ast.Attribute) else None)
            or (_forbidden_call(node) if isinstance(node, ast.Call) else None)
        )
        if found is not None:
            return found
        if isinstance(node, ast.Name) and aliases.get(node.id, "").split(".")[0] in _OS_MODULES:
            member = aliases[node.id].rpartition(".")[2]
            if "." in aliases[node.id] and _os_member_forbidden(member):
                return f"`{aliases[node.id]}`"
    return None


def _validate(source: str) -> str | None:
    """Kaynak çalıştırılabilir, sözleşmeye uygun ve güvenli mi?"""
    try:
        tree = ast.parse(source)
        compile(tree, "<forge>", "exec")
    except SyntaxError as hata:
        return f"Araç kaynağı geçersiz: Python sözdizimi hatası (satır {hata.lineno}): {hata.msg}"
    if not re.search(r"^def run\(", source, re.MULTILINE):
        return "Araç kaynağı `def run(args)` fonksiyonu tanımlamalı."
    yasak = _forbidden_use(tree)
    if yasak is not None:
        return (
            f"Üretilen araç {yasak} kullanamaz: araçlar dosya silemez/taşıyamaz, komut "
            "çalıştıramaz, ağa bağlanamaz ve ortam değişkenlerine/dinamik içe aktarmaya "
            "erişemez. Bu iş için run_shell kullan (onay ve geri alınabilir çöp oradadır)."
        )
    return None


def _builtins_for(context: ToolContext) -> dict[str, Any]:
    """Yerleşikler; `open` yolu kök kuralından geçirir (`path` adı taşımayan argüman da)."""

    def guarded_open(
        file: str | os.PathLike[str],
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> IO[Any]:
        if isinstance(file, int):
            raise PermissionError("Üretilen araç dosya tanıtıcısı (fd) ile açamaz.")
        writes = any(char in str(mode) for char in "wax+")
        resolved = writable_path(context, str(file)) if writes else resolve_path(context, str(file))
        return resolved.open(mode, buffering, encoding, errors, newline)

    return {**vars(builtins), "open": guarded_open}


def _clip(text: str) -> str:
    """Çıktıyı `MAX_OUTPUT_CHARS` ile sınırla (üretilen araç sınırsız metin döndürebilir)."""
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[:MAX_OUTPUT_CHARS] + f"\n[… {len(text) - MAX_OUTPUT_CHARS} karakter kırpıldı]"


_EMPTY_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}


def _contract(source: str, filename: str) -> tuple[str, dict[str, Any]]:
    """Modül belgesinden açıklama, modül düzeyi `SCHEMA` sabitinden parametre şeması.

    Ölçüldü (30 Ekim): şema hep boştu ve açıklama sabitti; model kaynağı görmeden
    aracı hangi argümanlarla çağıracağını bilemiyordu. `SCHEMA` yalnız `literal_eval`
    ile okunur (kod çalıştırılmaz); bozuk/geçersizse boş şemaya düşülür.
    """
    fallback = f"Koşu içinde üretilmiş araç ({filename})."
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return fallback, dict(_EMPTY_SCHEMA)
    doc = (ast.get_docstring(tree) or "").strip()
    description = doc.splitlines()[0][:300] if doc else fallback
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "SCHEMA" for t in node.targets
        ):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                break
            if isinstance(value, dict) and isinstance(value.get("properties"), dict):
                return description, {"type": "object", **value}
            break
    return description, dict(_EMPTY_SCHEMA)


def _build(path: Path) -> Tool:
    """Kaynağı yükleyip `Tool` sözleşmesine sar."""

    def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        namespace: dict[str, Any] = {"__builtins__": _builtins_for(context)}
        kaynak = _read(path)
        # Yükleme ile çağrı arasında dosya değişmiş olabilir: ÇALIŞTIRILACAK baytlar
        # onaylanan karmayla aynı olmalı ve yeniden denetlenmeli.
        trusted = trust.is_file_trusted(context.root, path, kaynak.encode("utf-8"))
        if not trusted or _validate(kaynak) is not None:
            return ToolResult.failure(
                f"{path.stem}: araç dosyası onaylandıktan sonra değişti; çalıştırılmadı."
            )
        try:
            exec(compile(kaynak, str(path), "exec"), namespace)
            islev = namespace.get("run")
            if not callable(islev):
                return ToolResult.failure(f"{path.stem}: `run` bulunamadı.")
            # Yol argümanları kök kuralından geçirilir: aracı ajan yazdı diye erişim
            # genişlemez; kök dışı yol burada reddedilir.
            for anahtar in ("path", "yol"):
                if isinstance(args.get(anahtar), str):
                    resolve_path(context, str(args[anahtar]))
            return ToolResult(_clip(str(islev(dict(args)))))
        except Exception as hata:  # araç sınırı: hata modele okunur biçimde döner
            return ToolResult.failure(f"{path.stem} çalışırken hata: {type(hata).__name__}: {hata}")

    description, parameters = _contract(_read(path), path.name)
    return Tool(
        name=path.stem,
        description=description,
        parameters=parameters,
        run=_run,
        mutating=True,
    )
