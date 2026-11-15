"""Agent'ın yazdığı betiği çalıştıran komut: "yaz -> sormadan çalıştır" zinciri (T1-06).

`write_file` onaysızdır; sonra `sh x.sh`, `python x.py`, `npm run x` ya da `make x` proje
dosyası sayılıp sorulmadan çalışıyordu. Betik içeriği hiç taranmıyordu (yalnız silme
kalıpları, yalnız Otomatik kipte). Ölçüldü (29 Ekim): `echo 'git push' > x.sh && sh x.sh`
için `is_unattended_safe` True, `auto_risk` None.

Her yazılmış betiği sormak "düzenle -> çalıştır -> doğrula" akışını bozar (26 Eylül
kullanıcı şikâyeti), bu yüzden betiğin İÇERİĞİ taranır ve yalnız riskliyse sorulur.
Taranan betik bu turda yazılmış (`ToolContext.touched`) ya da aynı komutta yönlendirmeyle
üretilmiş olmalıdır; depoda zaten var olan betik projenin kendi kodudur ve sorulmaz.
Bu bir kum havuzu DEĞİLDİR: dinamik oluşturulan komutlar (`subprocess.run(["git", "push"])`)
metin taramasından kaçar.
"""

from __future__ import annotations

import json
import posixpath
import re
from collections.abc import Iterable
from pathlib import Path

from .auto_policy import auto_risk, command_words, written_files
from .safety import danger_reason

#: Taranacak en büyük betik; daha büyüğü denetlenemez ve sorulur.
_MAX_BYTES = 512 * 1024
#: Betik dosyası alan yorumlayıcılar ve `source`.
_RUNNERS = frozenset(
    {"sh", "bash", "zsh", "dash", "ksh", "source", ".", "python", "python3", "node", "deno",
     "ruby", "perl", "php", "tsx", "ts-node"}
)  # fmt: skip
_SHELL_SUFFIXES = frozenset({".sh", ".bash", ".zsh", ""})
_JS_RUNNERS = frozenset({"npm", "pnpm", "yarn", "bun"})
_NPM_DIRECT = frozenset({"test", "start", "stop", "restart"})
#: Betik metninde (kabuk olmasa da) dışarıya iş yaptığını gösteren ifadeler.
_OUTWARD_TEXT = re.compile(
    r"\bgit\s+(?:-C\s+\S+\s+)?push\b|\b(?:npm|pnpm|yarn|bun|cargo|poetry)\s+publish\b|"
    r"\btwine\s+upload\b|\bdocker\s+push\b|"
    r"\bgh\s+(?:release|pr|repo|issue)\s+(?:create|merge|delete|edit|upload|close)\b|"
    r"\b(?:vercel|netlify|heroku|flyctl|wrangler|firebase)\b[^\n]*(?:\bdeploy\b|\bpublish\b|--prod)|"
    r"\bkubectl\s+(?:apply|delete)\b|\bterraform\s+(?:apply|destroy)\b|"
    r"\bcurl\b[^\n]*\s(?:-[A-Za-z]*[dFTX]\b|--(?:data|form|json|upload-file|request)\w*)|"
    r"\bwget\b[^\n]*--post-(?:data|file)|\bscp\b|\bssh\b|\brsync\b[^\n]*\S+@\S+:"
)


def script_chain_risk(command: str, root: Path | None, touched: Iterable[Path] = ()) -> str | None:
    """Komut, agent'ın yazdığı bir betiği çalıştırıyorsa ve içeriği riskliyse gerekçe."""
    if root is None:
        return None
    words = command_words(command)
    reason = _same_command_risk(command, words)
    if reason is not None:
        return reason
    written = {_resolved(path) for path in touched}
    if not written:
        return None
    for candidate in _executed_files(words):
        path = _resolved(root / Path(candidate).expanduser())
        if path in written:
            risk = _file_risk(path, root)
            if risk is not None:
                return f"bu turda yazdığın betik ({path.name}) {risk}"
    return _package_or_make_risk(words, root, written)


def _resolved(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path


def _same_command_risk(command: str, words: list[list[str]]) -> str | None:
    """Aynı komutta dosyaya yazıp o dosyayı çalıştıran zincir: içerik komut metnindedir."""
    written = {posixpath.normpath(target) for target in written_files(command)}
    if not written:
        return None
    ran = {posixpath.normpath(candidate) for candidate in _executed_files(words)}
    if not written & ran:
        return None
    risk = _text_risk(command)
    return None if risk is None else f"komut bir betik yazıp çalıştırıyor ve {risk}"


def _executed_files(words: list[list[str]]) -> list[str]:
    """Komutun çalıştırdığı betik dosyası adayları: `./x.sh`, `bash x.sh`, `python x.py`."""
    found: list[str] = []
    for parts in words:
        name = parts[0].rsplit("/", 1)[-1].rstrip("0123456789.") or parts[0]
        if "/" in parts[0] and not parts[0].startswith("-"):
            found.append(parts[0])
        elif name in _RUNNERS or parts[0] in _RUNNERS:
            script = _script_argument(parts[1:])
            if script is not None:
                found.append(script)
    return found


def _script_argument(arguments: list[str]) -> str | None:
    for argument in arguments:
        if argument == "-m":
            return None
        if not argument.startswith("-"):
            return argument
    return None


def _file_risk(path: Path, root: Path) -> str | None:
    try:
        if path.stat().st_size > _MAX_BYTES:
            return "denetlenemeyecek kadar büyük"
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if path.suffix.lower() in _SHELL_SUFFIXES or text.startswith(("#!/bin/sh", "#!/bin/bash")):
        return _shell_text_risk(text, root)
    return _text_risk(text)


def _text_risk(text: str) -> str | None:
    """Metin tehlikeli kalıp (DANGER_RULES) ya da dışa dönük iş içeriyor mu?"""
    reason = danger_reason("run_shell", {"command": text})
    if reason is not None:
        return f"{reason} içeriyor"
    match = _OUTWARD_TEXT.search(text)
    return None if match is None else f"dışarıya iş yapıyor (`{match.group(0).strip()}`)"


def _shell_text_risk(text: str, root: Path) -> str | None:
    """Kabuk betiği: önce metin kalıpları, sonra her satır Otomatik kipin risk tarayıcısından."""
    reason = _text_risk(text)
    if reason is not None:
        return reason
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            risk = auto_risk(stripped, root)
            if risk is not None:
                return f"{risk}"
    return None


def _package_or_make_risk(words: list[list[str]], root: Path, written: set[Path]) -> str | None:
    for parts in words:
        name = parts[0].rsplit("/", 1)[-1]
        if name in _JS_RUNNERS and _resolved(root / "package.json") in written:
            reason = _package_script_risk(name, parts[1:], root)
            if reason is not None:
                return reason
        if name == "make" and _resolved(root / "Makefile") in written:
            reason = _makefile_risk(parts[1:], root)
            if reason is not None:
                return reason
    return None


def _package_script_risk(manager: str, arguments: list[str], root: Path) -> str | None:
    positional = [a for a in arguments if not a.startswith("-")]
    if not positional:
        return None
    script = positional[1] if positional[0] == "run" and len(positional) > 1 else positional[0]
    if positional[0] != "run" and manager == "npm" and positional[0] not in _NPM_DIRECT:
        return None
    try:
        data = json.loads((root / "package.json").read_text(encoding="utf-8"))
        scripts = data.get("scripts", {})
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(scripts, dict):
        return None
    for key in (f"pre{script}", script, f"post{script}"):
        body = scripts.get(key)
        if isinstance(body, str):
            risk = _shell_text_risk(body, root)
            if risk is not None:
                return f"bu turda yazdığın package.json betiği ({key}) {risk}"
    return None


def _makefile_risk(arguments: list[str], root: Path) -> str | None:
    try:
        text = (root / "Makefile").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    targets = [a for a in arguments if not a.startswith("-") and "=" not in a]
    recipes = _recipes(text, targets) if targets else [text]
    for recipe in recipes:
        risk = _shell_text_risk(recipe, root)
        if risk is not None:
            return f"bu turda yazdığın Makefile hedefi {risk}"
    return None


def _recipes(makefile: str, targets: list[str]) -> list[str]:
    """Hedef adlarının tarif satırları (sekmeyle başlayan satırlar)."""
    found: list[str] = []
    lines = makefile.splitlines()
    for index, line in enumerate(lines):
        head = line.split(":", 1)[0].strip()
        if ":" in line and not line.startswith("\t") and head in targets:
            body = []
            for follow in lines[index + 1 :]:
                if not follow.startswith("\t"):
                    break
                body.append(follow.strip())
            found.append("\n".join(body))
    return found
