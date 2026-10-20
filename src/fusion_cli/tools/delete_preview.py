"""Silmenin ÖNİZLEMESİ: onay kartı metni ve otomatik kipte sorulacak silmeler.

`safe_delete` silmeyi YAPAR (çöpe taşır); bu modül silmeden ÖNCE kullanıcıya ne
gideceğini ve otomatik kipin neyi sorması gerektiğini söyler.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from .safe_delete import (
    caution_reason,
    expand_targets,
    forbidden_reason,
    is_complex_recursive_delete,
    is_container_root,
    simple_rm_targets,
)

#: 20.000: tipik bir node_modules'ü saymaya yeter, onay kartını bekletmez (ölçüm
#: yok; dosya sistemi gezintisi saniyede on binlerce girdi okur).
PREVIEW_MAX_ENTRIES = 20_000
#: Kartta tek tek gösterilecek en fazla hedef (`rm ./*` yüzlerce öğe açabilir).
PREVIEW_MAX_TARGETS = 8


def describe_delete(command: str, root: Path, home: Path) -> str:
    """Silme komutunun onay kartında görünecek açıklaması: tam yol, boyut, akıbet.

    Ölçüldü (1 Ekim olayı): kart `rm -rf ./*` gösteriyordu; kullanıcı "projeyi sil"
    dediği için onaylanabilir görünüyordu, oysa hedef bütün Masaüstüydü.
    """
    targets = simple_rm_targets(command)
    if targets is None:
        if is_complex_recursive_delete(command):
            return "Bu biçimdeki silme çöpe GİTMEZ, KALICI olur (geri alınamaz)."
        return ""
    lines: list[str] = []
    paths = expand_targets(targets, root)
    for path in paths[:PREVIEW_MAX_TARGETS]:
        path = path.resolve()
        yasak = forbidden_reason(path, home)
        if yasak is not None:
            lines.append(f"{path} — SİLİNEMEZ ({yasak})")
            continue
        if not path.exists():
            lines.append(f"{path} — zaten yok")
            continue
        dikkat = caution_reason(path, root, home)
        onek = f"DİKKAT: {dikkat} — " if dikkat else ""
        lines.append(f"{path} — {onek}{_size_text(path)} → Fusion çöpüne taşınır (geri alınabilir)")
    if len(paths) > PREVIEW_MAX_TARGETS:
        lines.append(f"… ve {len(paths) - PREVIEW_MAX_TARGETS} hedef daha")
    return "Hedef: " + "; ".join(lines)


def delete_caution(command: str, root: Path, home: Path) -> str | None:
    """Sade `rm` hedeflerinden biri dikkat gerektiriyorsa ilk gerekçe (yoksa None).

    Proje içindeki sıradan bir dosya/klasör silmesi çöpe gittiği için sorulmaz;
    proje dışı, kökün kendisi/üstü, Masaüstü gibi yerler otomatik kipte sorulur.
    """
    targets = simple_rm_targets(command)
    if targets is None:
        return None
    for path in expand_targets(targets, root):
        reason = forbidden_reason(path, home) or caution_reason(path, root, home)
        if reason is not None:
            return f"silme hedefi {reason}"
    return None


def _size_text(path: Path) -> str:
    if not path.is_dir():
        return _human_bytes(path.stat().st_size)
    count = 0
    total = 0
    for item in path.rglob("*"):
        count += 1
        if count > PREVIEW_MAX_ENTRIES:
            return f"{PREVIEW_MAX_ENTRIES:,}+ öğe".replace(",", ".")
        if item.is_file() and not item.is_symlink():
            total += item.stat().st_size
    return f"{count} öğe, {_human_bytes(total)}"


def _human_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


#: Betik çalıştırıcıları ve içerikte aranacak silme/taşıma desenleri.
_SCRIPT_RUNNERS = frozenset(
    {"python", "python3", "node", "bash", "sh", "zsh", "php", "ruby", "perl"}
)
_SCRIPT_DELETE = re.compile(
    r"shutil\.(rmtree|move)|os\.(remove|unlink|rmdir|removedirs|rename|replace)\b|"
    r"\.unlink\(|\.rmdir\(|\.(?:rm|rmSync|unlinkSync|rmdirSync|rename|renameSync)\s*\(|"
    r"\brimraf\b|\brm\s+-[a-zA-Z]*[rRf]|\bfind\b.*-delete|\bunlink\s*\(|\brmdir\s*\(|"
    r"\bsend2trash\b"
)
#: Okunacak en fazla betik boyutu; daha büyüğü denetlenemez, yine sorulur.
_SCRIPT_MAX_BYTES = 512 * 1024


#: Betiğin proje DIŞINA uzandığını gösteren izler: ev dizini, mutlak kullanıcı
#: yolu, üst klasör. Bunlar yoksa betik yalnız kendi projesinde iş görür.
_SCRIPT_OUTSIDE = re.compile(
    r"expanduser|Path\.home\(|~/|\$HOME|\$\{HOME\}|environ\W+HOME|/Users/|/home/|\.\./"
    r"|homedir\(|process\.env\.HOME|getenv\(\W*HOME"
)


def script_danger(command: str, root: Path, home: Path | None = None) -> str | None:
    """Komut bir betik çalıştırıyorsa ve betik riskli yerde siliyorsa gerekçe.

    Ölçüldü (1 Ekim olayı): Masaüstünde çalışan `python3 sil.py` otomatik kipte
    "projenin kendi betiği" sayılıp sorulmadan çalıştı. Betikle silinen çöpe
    GİTMEZ. Ama projenin kendi temizlik betiği (`shutil.rmtree("dist")`) her
    seferinde sorulursa otomatik kip anlamsızlaşır; bu yüzden yalnız iki durumda
    sorulur: çalışılan klasör bir proje deposuysa (Masaüstü gibi) ya da betik
    ev dizinine/mutlak yollara/üst klasöre uzanıyorsa.
    """
    path = _script_path(command, root)
    if path is None:
        return None
    try:
        if path.stat().st_size > _SCRIPT_MAX_BYTES:
            return f"betik ({path.name}) denetlenemeyecek kadar büyük"
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    tehlike = _code_danger(content, root, home)
    return None if tehlike is None else f"betik ({path.name}) {tehlike}"


def inline_code_danger(code: str) -> str | None:
    """`python -c`/`node -e` ile verilen satır içi kod dosya siliyor/taşıyor mu?

    Proje betiğinden farklı olarak satır içi silme kodu olağan değildir ve hedefi
    kartta okunamaz; her zaman sorulur.
    """
    match = _SCRIPT_DELETE.search(code)
    if match is None:
        return None
    return (
        f"satır içi kod dosya siliyor/taşıyor (`{match.group(0)}`); bu yolla silinen "
        "Fusion çöpüne GİTMEZ, geri alınamaz"
    )


def _code_danger(content: str, root: Path, home: Path | None) -> str | None:
    """Kod metni silme/taşıma içeriyor VE proje deposunda ya da proje dışına uzanıyorsa."""
    match = _SCRIPT_DELETE.search(content)
    if match is None:
        return None
    depo = is_container_root(root, home if home is not None else Path.home())
    if not depo and _SCRIPT_OUTSIDE.search(content) is None:
        return None
    yer = "birden çok proje içeren klasörde" if depo else "proje dışına uzanan yollarla"
    return (
        f"{yer} dosya siliyor/taşıyor (`{match.group(0)}`); bu yolla silinen Fusion "
        "çöpüne GİTMEZ, geri alınamaz"
    )


def _script_path(command: str, root: Path) -> Path | None:
    """`python3 x.py`, `bash x.sh` gibi bir komutun çalıştırdığı betik dosyası."""
    try:
        parts = shlex.split(command)
    except ValueError:
        return None
    runners = {name.rstrip("0123456789.") for name in _SCRIPT_RUNNERS}
    if len(parts) < 2 or parts[0].rsplit("/", 1)[-1].rstrip("0123456789.") not in runners:
        return None
    script = next((part for part in parts[1:] if not part.startswith("-")), None)
    return None if script is None else (root / Path(script).expanduser()).resolve()
