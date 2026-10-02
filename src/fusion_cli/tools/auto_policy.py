"""Otomatik kipin kararı — Claude'daki "Auto" gibi: riskli değilse SORMA.

`command_policy.is_unattended_safe` bir beyaz listedir ve "Düzenlemeleri kabul et"
kipinin temelidir: tanımadığı her komutu sorar. Otomatik kip eskiden de ona
bakıyordu; `php -l`, `lsof -i :3000`, `unzip`, `wget`, bir `for` döngüsü bile
soruluyordu. Kullanıcı (2 Ekim 2026): "otomatik modunda bile bazen gereksiz
yerlerde bana soru soruyor, sormasın".

Burada karar tersine döner: projede iş gören komut sorulmaz. Yalnız şunlar sorulur:

- proje DIŞINA yazma/taşıma ve proje dışındaki klasörde değişiklik,
- sistem geneli değişiklik (sudo, global kurulum, launchctl, defaults write…),
- dışarıya yayın/gönderim (git push, publish, deploy, uzak sunucu, veri POST'u),
- veritabanı silme ve uygulamaları ada göre kapatma.

Geri alınamaz yerel kayıplar ve sır okuma `safety.DANGER_RULES`'tadır (bu kipte de
sorulur); sade `rm` çöpe gider (`safe_delete`), dikkat gerektiren silme hedefini
`delete_preview.delete_caution` söyler. Bu bir kum havuzu DEĞİLDİR: karar yalnız
SORULUP sorulmayacağıdır.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from .command_paths import escapes_project
from .command_policy import (
    CURL_SEND_FLAGS,
    GLOBAL_INSTALL_FLAGS,
    READ_ONLY_COMMANDS,
    READONLY_GIT_SUBCOMMANDS,
    is_outward_script,
    only_local_urls,
)
from .delete_preview import inline_code_danger

#: Komutun önüne gelip asıl komutu değiştirmeyen sözcükler (`time`, `nohup`, `do`).
_PREFIX_WORDS = frozenset(
    {"time", "nohup", "exec", "command", "builtin", "env", "then", "do", "else", "!", "{", "("}
)
#: Sistem ayarını/aygıtı değiştiren komutlar.
_SYSTEM_COMMANDS = frozenset(
    {
        "launchctl", "diskutil", "csrutil", "nvram", "systemsetup", "pmset", "scutil",
        "networksetup", "spctl", "tccutil", "crontab", "osascript", "systemctl", "service",
        "chown", "chflags", "dscl", "kextload", "softwareupdate",
    }
)  # fmt: skip
#: Sistem paket yöneticileri (kurulum makinenin geneline gider).
_SYSTEM_PACKAGERS = frozenset({"brew", "apt", "apt-get", "yum", "dnf", "pacman", "port", "snap"})
_SYSTEM_PACKAGER_READS = frozenset(
    {"list", "info", "search", "show", "--version", "doctor", "config"}
)
#: Proje dışına (kullanıcının PATH'ine) araç kuran komutlar.
_GLOBAL_TOOL_INSTALLS = {"gem": "install", "cargo": "install", "go": "install", "pipx": "install"}
#: Bağlandığı her yer uzak sunucu olan komutlar.
_REMOTE_COMMANDS = frozenset({"ssh", "scp", "sftp", "ftp", "telnet", "mosh"})
#: Bulut/dağıtım araçları: her çağrısı bir hesaba dokunur.
_DEPLOY_COMMANDS = frozenset(
    {"vercel", "netlify", "heroku", "flyctl", "fly", "surge", "aws", "gcloud", "az", "doctl"}
)
#: Alt komutu dışarıya yazan araçlar: araç → yazan alt komutlar.
_OUTWARD_SUBCOMMANDS = {
    "firebase": {"deploy", "hosting:channel:deploy"},
    "wrangler": {"deploy", "publish"},
    "eas": {"submit", "update", "build"},
    "docker": {"push", "login"},
    "kubectl": {"apply", "delete", "create", "patch", "scale", "rollout", "replace"},
    "terraform": {"apply", "destroy"},
    "helm": {"install", "upgrade", "uninstall", "rollback"},
    "twine": {"upload"},
    "supabase": {"deploy", "push"},
}
#: `gh` ile GitHub'da bir şey değiştiren eylemler.
_GH_WRITES = frozenset(
    {"create", "merge", "close", "delete", "edit", "comment", "review", "upload", "fork"}
)
#: Veritabanını silen ifadeler (SQL ya da çerçeve komutu).
_DB_DROP = re.compile(
    r"(?i)\bdrop\s+(database|schema|table)\b|\btruncate\s+table\b|\bdb:drop\b|"
    r"\bmigrate:(fresh|reset)\b|\bmigrate\s+reset\b|\bdropdb\b"
)
#: Yazdığı yer yalnız SON konumsal argüman olan komutlar (kaynaklar yalnız okunur).
_DEST_LAST = frozenset({"cp", "ln", "install", "rsync"})
#: Betik çalıştıranlar ve betik uzantıları (`bash deploy.sh`, `./release.py`).
_SCRIPT_RUNNERS = frozenset({"bash", "sh", "zsh", "python", "python3", "node"})
_SCRIPT_SUFFIXES = (".sh", ".py", ".js", ".mjs", ".ts")
#: Proje dışında olsa da yazılması zararsız geçici dizinler.
_SCRATCH_PREFIXES = ("/tmp/", "/private/tmp/", "/var/folders/", "/dev/null")
#: Yönlendirme hedefi: `> x`, `>> x`, `2> x`, `&> x` (`>&1` değil).
_REDIRECT = re.compile(r"(?<![<>])(?:\d|&)?>{1,2}(?!&)\s*([^\s;&|<>()]+)")
_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_HOME_VAR = re.compile(r"\$\{?(HOME|USER)\b")


def auto_risk(command: str, root: Path | None) -> str | None:
    """Otomatik kipte bu komut SORULMALI mı? Gerekçe ya da None (sormadan çalışır)."""
    if not command.strip():
        return None
    for target in _REDIRECT.findall(_unquoted(command)):
        if _outside(target, root):
            return f"proje dışına yazıyor ({target})"
    away = False
    for segment in _segments(command):
        parts = _words(segment)
        if not parts:
            continue
        name, arguments = parts[0].rsplit("/", 1)[-1], parts[1:]
        if name == "cd":
            away = bool(arguments) and _outside(arguments[0], root)
            continue
        reason = _segment_risk(name, arguments, segment, root)
        if reason is None and away and not _reads_only(name, arguments):
            reason = "proje dışındaki bir klasörde değişiklik yapıyor"
        if reason is not None:
            return reason
    return None


def is_read_only_command(command: str) -> bool:
    """Komut YALNIZ okuyor mu? (Plan ve Manuel kipte sorulmadan çalışır.)

    Dosyaya yönlendirme, alt kabuk ve yazan bayraklar (`sed -i`, `find -delete`)
    okumayı yazmaya çevirir.
    """
    cleaned = re.sub(r"\d?>\s*/dev/null|2>&1|&>\s*/dev/null", "", command)
    if not cleaned.strip() or ">" in _unquoted(cleaned) or "$(" in cleaned or "`" in cleaned:
        return False
    for segment in _segments(cleaned):
        parts = _words(segment)
        if not parts or not _reads_only(parts[0].rsplit("/", 1)[-1], parts[1:]):
            return False
    return True


def _segment_risk(name: str, arguments: list[str], segment: str, root: Path | None) -> str | None:
    """Tek bir komut parçasının riski (sıra: yetki, sistem, dışarı, yol)."""
    sub = next((a for a in arguments if not a.startswith("-")), "")
    if name in {"sudo", "doas", "su"}:
        return "yönetici yetkisi (sudo) istiyor"
    if name in _SYSTEM_COMMANDS or (name == "defaults" and sub in {"write", "delete"}):
        return "sistem ayarını değiştiriyor"
    if name in {"env", "printenv"} or (name == "set" and not arguments):
        return "ortam değişkenlerini (API anahtarları dahil) döküyor"
    reason = _install_risk(name, arguments, sub) or _outward_risk(name, arguments, sub)
    if reason is not None:
        return reason
    if name == "killall":
        return "uygulamaları ada göre kapatıyor"
    if _DB_DROP.search(segment):
        return "veritabanını/tabloyu siliyor"
    code = _inline_code(name, arguments)
    tehlike = inline_code_danger(code) if code is not None else None
    if tehlike is not None:
        return tehlike
    if not _reads_only(name, arguments) and any(
        _outside(target, root) for target in _write_targets(name, arguments)
    ):
        return "proje dışındaki bir yolu değiştiriyor"
    return None


def _install_risk(name: str, arguments: list[str], sub: str) -> str | None:
    if name in _SYSTEM_PACKAGERS and sub and sub not in _SYSTEM_PACKAGER_READS:
        return f"sisteme paket kuruyor/kaldırıyor ({name} {sub})"
    uv_tool = name == "uv" and arguments[:2] == ["tool", "install"]
    if _GLOBAL_TOOL_INSTALLS.get(name) == sub or uv_tool:
        return f"proje dışına araç kuruyor ({name} {sub})"
    if name in {"npm", "pnpm", "yarn", "bun", "pip", "pip3"} and (
        any(argument in GLOBAL_INSTALL_FLAGS for argument in arguments) or sub == "global"
    ):
        return "sistem geneline (global) kuruyor"
    return None


def _outward_risk(name: str, arguments: list[str], sub: str) -> str | None:
    """Dışarıya yayın, dağıtım, uzak sunucu ya da veri gönderimi."""
    if name == "git" and "push" in arguments:
        return "uzak depoya gönderiyor (git push)"
    if sub == "publish" or (name in {"npm", "pnpm", "yarn", "bun"} and _outward_run(arguments)):
        return f"dışarıya yayınlıyor ({name} {sub})"
    if name in _DEPLOY_COMMANDS or sub in _OUTWARD_SUBCOMMANDS.get(name, ()):
        return f"bulut/dağıtım hesabında işlem yapıyor ({name})"
    if name == "gh" and any(argument in _GH_WRITES for argument in arguments[1:3]):
        return "GitHub'da değişiklik yapıyor (gh)"
    if name in _REMOTE_COMMANDS or (name == "rsync" and any(_is_remote(a) for a in arguments)):
        return f"uzak sunucuya bağlanıyor ({name})"
    if name in {"curl", "wget"} and _sends_data(name, arguments):
        return f"dışarıya veri gönderiyor ({name})"
    script = sub if name in _SCRIPT_RUNNERS else name
    if script.endswith(_SCRIPT_SUFFIXES) and is_outward_script(script):
        return f"dağıtım/yayın betiği ({script})"
    return None


def _outward_run(arguments: list[str]) -> bool:
    """`npm run deploy` gibi adı dışa dönük iş söyleyen paket betiği mi?"""
    return len(arguments) >= 2 and arguments[0] == "run" and is_outward_script(arguments[1])


def _sends_data(name: str, arguments: list[str]) -> bool:
    if name == "wget":
        sends = any(a.startswith(("--post-data", "--post-file", "--method")) for a in arguments)
    else:
        sends = any(
            a in CURL_SEND_FLAGS or a.startswith(("--data", "-d@", "--json")) for a in arguments
        )
    return sends and not only_local_urls(arguments)


def _is_remote(argument: str) -> bool:
    """rsync/scp hedefi `kullanıcı@sunucu:yol` ya da `sunucu:yol` mu?"""
    if argument.startswith(("-", "/", ".")):
        return False
    return re.match(r"^[\w.@-]+:", argument) is not None


def _reads_only(name: str, arguments: list[str]) -> bool:
    """Bu parça yalnız okuyor mu?"""
    if name == "git":
        return bool(arguments) and arguments[0] in READONLY_GIT_SUBCOMMANDS
    if name == "sed":
        return not any(a.startswith("-i") or a == "--in-place" for a in arguments)
    if name == "find":
        return not any(a in {"-delete", "-exec", "-execdir", "-ok", "-fprint"} for a in arguments)
    if name == "php":
        return arguments[:1] in (["-l"], ["-v"], ["--version"])
    if name in {"node", "python", "python3"}:
        return arguments[:1] in (["--version"], ["-V"], ["--check"])
    return name in READ_ONLY_COMMANDS or name in {"lsof", "cd", "for", "if", "while", "done", "fi"}


def _write_targets(name: str, arguments: list[str]) -> list[str]:
    """Komutun YAZABİLECEĞİ argümanlar: kopyalamada yalnız hedef, ötekilerde hepsi."""
    positional = [a for a in arguments if not a.startswith("-")]
    if name in _DEST_LAST:
        return positional[-1:]
    return arguments


def _outside(token: str, root: Path | None) -> bool:
    """Yol proje dışında mı? Döngü değişkeni (`$f`) bilinmez ama dışarı sayılmaz."""
    if "$" in token:
        return _HOME_VAR.search(token) is not None
    if "://" in token or token.startswith(_SCRATCH_PREFIXES) or token == "/tmp":
        return False
    return escapes_project("cp", [token], root)


def _inline_code(name: str, arguments: list[str]) -> str | None:
    """`python -c`, `node -e`, `php -r` gibi satır içi kodun metni."""
    flags = {"-c"} if name.startswith("python") else {"-e", "--eval", "-r"}
    for index, argument in enumerate(arguments[:-1]):
        if argument in flags:
            return arguments[index + 1]
    return None


def _words(segment: str) -> list[str]:
    """Parçayı sözcüklere ayır; öndeki atamaları ve `time`/`do` gibi önekleri at."""
    try:
        parts = shlex.split(segment)
    except ValueError:
        parts = segment.split()
    while len(parts) > 1 and (parts[0] in _PREFIX_WORDS or _ENV_ASSIGN.match(parts[0])):
        parts = parts[1:]
    if parts[:1] == ["xargs"]:
        parts = [a for a in parts[1:] if not a.startswith("-")]
    return parts


def _segments(command: str) -> list[str]:
    """Komutu `;`, `&&`, `||`, `|`, satır sonu ve alt kabuk (`$(…)`, ters tırnak) sınırlarından böl.

    Tırnak içi bölünmez: `python3 -c "a; b"` tek parçadır.
    """
    pieces: list[str] = []
    current: list[str] = []
    quote = ""
    for char in command.replace("$(", "("):
        if quote:
            quote = "" if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char in ";|&\n`()":
            pieces.append("".join(current))
            current = []
            continue
        current.append(char)
    pieces.append("".join(current))
    return [piece.strip() for piece in pieces if piece.strip()]


def _unquoted(command: str) -> str:
    """Tırnak içini boşaltılmış komut: `grep ">" a` içindeki `>` yönlendirme değildir."""
    return re.sub(r"'[^']*'|\"[^\"]*\"", "''", command)
