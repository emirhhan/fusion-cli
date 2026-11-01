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
from collections.abc import Iterator
from pathlib import Path

from .command_paths import escapes_project
from .command_policy import (
    _FIND_UNSAFE,
    GLOBAL_INSTALL_FLAGS,
    READ_ONLY_COMMANDS,
    curl_sends_data,
    is_outward_script,
    only_local_urls,
)
from .command_semantics import awk_reads_only, git_reads_only, sed_reads_only
from .delete_preview import inline_code_danger
from .github_cli import gh_reads_only

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
#: Uzak hesapta kaynak silen/kaldıran araçlar ve alt komut fiilleri (`kubectl delete`,
#: `aws ec2 terminate-instances`, `heroku apps:destroy`, `terraform apply -destroy`,
#: `gh api -X DELETE`). `docker` yerel kapsayıcı da sildiği için dışarıda tutulur.
_REMOTE_DELETERS = _DEPLOY_COMMANDS | {
    "kubectl", "terraform", "helm", "firebase", "wrangler", "supabase", "eas", "gh",
}  # fmt: skip
_REMOTE_DELETE_VERB = re.compile(
    r"(?i)(?:^|[-:])(delete|destroy|terminate|uninstall|remove|purge|deregister)(?=$|[-:])"
)
#: Fiil yalnız ilk birkaç sözcükte aranır; sonrası kaynak adıdır (`kubectl delete ns prod`).
_REMOTE_DELETE_SCAN = 5
#: `gh` ile GitHub'da bir şey değiştiren eylemler (komuttan bağımsız alt komut adları).
_GH_WRITES = frozenset(
    {
        "create",
        "merge",
        "close",
        "delete",
        "edit",
        "comment",
        "review",
        "upload",
        "fork",
        "reopen",
        "lock",
        "unlock",
        "ready",
        "transfer",
        "pin",
        "unpin",
        "set",
        "enable",
        "disable",
        "cancel",
        "rerun",
        "sync",
        "rename",
        "archive",
        "unarchive",
    }
)
#: Yalnız belirli `gh <komut>` altında yazma anlamına gelen alt komutlar: `gh workflow run`
#: iş akışı tetikler, `gh run list` ise okur. Ölçüldü (31 Ekim): `gh workflow run` ve
#: `gh api -X POST` onaysız geçiyordu; `api` için `github_cli.gh_reads_only` kapısı kullanılır.
_GH_COMMAND_WRITES: dict[str, frozenset[str]] = {
    "workflow": frozenset({"run"}),
    "cache": frozenset({"delete"}),
}
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
#: Başka bir komutu kendi adına çalıştıran kabuklar (`sh -c '…'`) ve sarmalayıcılar.
_SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh"})
_SHELL_C_FLAGS = re.compile(r"^-[A-Za-z]*c[A-Za-z]*$")
#: Sarmalayıcı → değer alan seçenekleri ve atlanacak konumsal sayısı (`timeout 30 …`).
_WRAPPERS: dict[str, tuple[frozenset[str], int]] = {
    "timeout": (frozenset({"-s", "-k", "--signal", "--kill-after"}), 1),
    "nice": (frozenset({"-n", "--adjustment"}), 0),
    "caffeinate": (frozenset({"-t", "-w"}), 0),
    "watch": (frozenset({"-n", "--interval"}), 0),
}
#: Önek sözcüklerin değer alan seçenekleri (`env -u AD komut`, `xargs -n 1 komut`).
_PREFIX_VALUE_FLAGS = {
    "env": frozenset({"-u", "-C", "-S", "-P", "--unset", "--chdir"}),
    "xargs": frozenset({"-n", "-I", "-L", "-P", "-s", "-d", "-E", "-a", "-J"}),
}
#: İç içe komutun en fazla derinliği; aşılırsa belirsiz sayılıp sorulur.
_MAX_NESTING = 4
#: Çıktıyı kabuğa/yorumlayıcıya boşaltan boru: `curl … | sh`, `| python3`, `| sudo bash`.
#: Betik dosyası ya da `-c '…'` alan yorumlayıcı bu desene girmez.
_PIPE_TO_INTERPRETER = re.compile(
    r"\|\s*(?:(?:sudo|env)\s+)*(?:sh|bash|zsh|dash|ksh|python[\d.]*|node|perl|ruby|php)"
    r"(?:\s+-[\w-]*)*\s*(?=$|[;&|)\n])"
)
#: Çift tırnak içinde bile çalışan komut ikamesi: `"$(git push)"`, `"`git push`"`.
_SUBSTITUTION = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")
#: Satır içi kodun komut çalıştırdığını ya da ağa bağlandığını gösteren izler.
_INLINE_OUTWARD = re.compile(
    r"\bsubprocess\b|\bos\.(?:system|popen|exec\w*|spawn\w*)|\bpty\b|\bsocket\b|"
    r"\burllib\b|\brequests\b|\bhttp\.client\b|\bhttpx\b|\baiohttp\b|\bsmtplib\b|"
    r"\bftplib\b|\bchild_process\b|\bexecSync\b|\bspawnSync\b|\bfetch\s*\(|"
    r"\bXMLHttpRequest\b|\baxios\b|\bsystem\s*\(|\bpopen\b|\bexec\s*[(\"']"
)
_INTERPRETERS = frozenset({"node", "deno", "perl", "ruby", "php"})
_HOME_VAR = re.compile(r"\$\{?(HOME|USER)\b")


def auto_risk(command: str, root: Path | None) -> str | None:
    """Otomatik kipte bu komut SORULMALI mı? Gerekçe ya da None (sormadan çalışır).

    İç içe komut (`sh -c '…'`, `eval`, `timeout 5 …`, `"$(…)"`) özyinelemeli çözülür:
    ölçüldü (29 Ekim), eskiden `sh -c 'git push'` içteki komuta hiç bakılmadan geçiyordu.
    """
    return next(_risks(command, root, 0), None)


def auto_risks(command: str, root: Path | None) -> tuple[str, ...]:
    """Komuttaki BÜTÜN risk gerekçeleri (sırayla, tekrarsız).

    Denetçi (P-011) yalnız ilk gerekçeye bakarsa `git push && sudo …` zincirindeki sudo
    modele bırakılırdı; sabit riskler (`is_fixed_risk`) her parçada aranır.
    """
    return tuple(dict.fromkeys(_risks(command, root, 0)))


#: Hiçbir zaman denetçi modeline bırakılmayan, kuralın kesin sorduğu gerekçeler (P-011).
SUDO_REASON = "yönetici yetkisi (sudo) istiyor"
SYSTEM_SETTING_REASON = "sistem ayarını değiştiriyor"
ENV_DUMP_REASON = "ortam değişkenlerini (API anahtarları dahil) döküyor"
PIPE_TO_SHELL_REASON = "çıktıyı kabuğa/yorumlayıcıya boşaltıyor (… | sh) — içeriği denetlenemiyor"
VARIABLE_COMMAND_REASON = "komut adı bir değişkenden geliyor (ne çalışacağı bilinmiyor)"
NESTING_REASON = "iç içe çok katmanlı komut (içeriği denetlenemiyor)"
KILLALL_REASON = "uygulamaları ada göre kapatıyor"
DB_DROP_REASON = "veritabanını/tabloyu siliyor"
INLINE_OUTWARD_REASON = "satır içi kod komut çalıştırıyor ya da ağa bağlanıyor"
#: Uzak hesapta kaynak silme (`kubectl delete`, `terraform destroy`, `gh repo delete`):
#: MCP'nin `REMOTE_DESTRUCTIVE` etkisinin kabuk karşılığı; hiçbir ayarda modele bırakılmaz.
REMOTE_DELETE_REASON = "uzakta geri alınamaz silme yapıyor ({name} {verb})"
FIXED_RISK_REASONS = frozenset(
    {
        SUDO_REASON,
        SYSTEM_SETTING_REASON,
        ENV_DUMP_REASON,
        PIPE_TO_SHELL_REASON,
        VARIABLE_COMMAND_REASON,
        NESTING_REASON,
        KILLALL_REASON,
        DB_DROP_REASON,
        INLINE_OUTWARD_REASON,
    }
)
#: Başka modüllerin ürettiği, aynı sınıftaki gerekçelerin başı: dikkat gerektiren silme
#: (`delete_preview.delete_caution`), satır içi silme kodu (`inline_code_danger`) ve bu turda
#: yazılmış betiğin riski (`script_chain`) — içerik modele gösterilmez, karar kurala kalır.
FIXED_RISK_PREFIXES = (
    "silme hedefi ",
    "satır içi kod ",
    "bu turda yazdığın betik ",
    REMOTE_DELETE_REASON.split("(", 1)[0],
)


def is_fixed_risk(reason: str) -> bool:
    """Gerekçe denetçiye bırakılamayan (her zaman sorulan) sınıftan mı?"""
    return reason in FIXED_RISK_REASONS or reason.startswith(FIXED_RISK_PREFIXES)


def _risks(command: str, root: Path | None, depth: int) -> Iterator[str]:
    if not command.strip():
        return
    if depth > _MAX_NESTING:
        yield NESTING_REASON
        return
    unquoted = _unquoted(command)
    for target in _REDIRECT.findall(unquoted):
        if _outside(target, root):
            yield f"proje dışına yazıyor ({target})"
    if _PIPE_TO_INTERPRETER.search(unquoted):
        yield PIPE_TO_SHELL_REASON
    for match in _SUBSTITUTION.finditer(re.sub(r"'[^']*'", "''", command)):
        yield from _risks(match.group(1) or match.group(2) or "", root, depth + 1)
    away = False
    for segment in _segments(command):
        parts = _words(segment)
        if not parts:
            continue
        name, arguments = parts[0].rsplit("/", 1)[-1], parts[1:]
        if name == "cd":
            away = bool(arguments) and _outside(arguments[0], root)
            continue
        found = False
        for reason in _segment_risks(name, arguments, segment, root, depth):
            found = True
            yield reason
        if not found and away and not _reads_only(name, arguments):
            yield "proje dışındaki bir klasörde değişiklik yapıyor"


def command_words(command: str) -> list[list[str]]:
    """Komutun her parçası için sözcükler (`_segments` + `_words`); boş parçalar atılır."""
    return [parts for segment in _segments(command) if (parts := _words(segment))]


def written_files(command: str) -> list[str]:
    """Komutun dosyaya YAZDIĞI adlar: yönlendirme hedefleri ve `tee` argümanları."""
    targets = list(_REDIRECT.findall(_unquoted(command)))
    for parts in command_words(command):
        if parts[0] == "tee":
            targets.extend(a for a in parts[1:] if not a.startswith("-"))
    return targets


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


def _segment_risks(
    name: str, arguments: list[str], segment: str, root: Path | None, depth: int = 0
) -> Iterator[str]:
    """Tek bir komut parçasının riskleri (sıra: yetki, sistem, dışarı, iç içe, yol).

    İlk gerekçe eski tek-sonuçlu sırayla aynıdır (`auto_risk` onu kullanır).
    """
    sub = next((a for a in arguments if not a.startswith("-")), "")
    if name in {"sudo", "doas", "su"}:
        yield SUDO_REASON
        # Yetki öneki asıl komutu sarar: `sudo git push` → içteki komut da değerlendirilir.
        yield from _risks(" ".join(shlex.quote(part) for part in arguments), root, depth + 1)
        return
    if name in _SYSTEM_COMMANDS or (name == "defaults" and sub in {"write", "delete"}):
        yield SYSTEM_SETTING_REASON
    if name in {"env", "printenv"} or (name == "set" and not arguments):
        yield ENV_DUMP_REASON
    reason = _install_risk(name, arguments, sub) or _outward_risk(name, arguments, sub)
    if reason is not None:
        yield reason
    if name.startswith("$"):
        yield VARIABLE_COMMAND_REASON
        return
    nested = _nested_command(name, arguments)
    if nested is not None:
        yield from _risks(nested, root, depth + 1)
        return
    if name == "killall":
        yield KILLALL_REASON
    if _DB_DROP.search(segment):
        yield DB_DROP_REASON
    code = _inline_code(name, arguments)
    tehlike = inline_code_danger(code) if code is not None else None
    if tehlike is not None:
        yield tehlike
    inline_runner = name.startswith("python") or name in _INTERPRETERS
    if code is not None and inline_runner and _INLINE_OUTWARD.search(code):
        yield INLINE_OUTWARD_REASON
    if not _reads_only(name, arguments) and any(
        _outside(target, root) for target in _write_targets(name, arguments)
    ):
        yield "proje dışındaki bir yolu değiştiriyor"


def nested_command(name: str, arguments: list[str]) -> str | None:
    """Komutun kendi adına çalıştırdığı iç komut: `sh -c '…'`, `eval …`, `timeout 5 …`.

    İzin kuralı eşlemesi (`permission_match`) de aynı çözücüyü kullanır: deny kuralı
    sarmalayıcıyla aşılmasın (ölçüldü, 31 Ekim: `bash -c 'rm x'` deny bulmuyordu).
    """
    return _nested_command(name, arguments)


def _nested_command(name: str, arguments: list[str]) -> str | None:
    if name in _SHELLS:
        for index, argument in enumerate(arguments[:-1]):
            if _SHELL_C_FLAGS.match(argument):
                return arguments[index + 1]
        return None
    if name == "eval":
        return " ".join(arguments)
    wrapper = _WRAPPERS.get(name)
    if wrapper is None:
        return None
    value_flags, skip = wrapper
    rest = list(arguments)
    while rest and rest[0].startswith("-"):
        rest = rest[2:] if rest[0] in value_flags else rest[1:]
    return " ".join(shlex.quote(part) for part in rest[skip:]) or None


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
    verb = _remote_delete_verb(name, arguments)
    if verb is not None:
        return REMOTE_DELETE_REASON.format(name=name, verb=verb)
    if name in _DEPLOY_COMMANDS or sub in _OUTWARD_SUBCOMMANDS.get(name, ()):
        return f"bulut/dağıtım hesabında işlem yapıyor ({name})"
    if name == "gh" and _gh_writes(arguments):
        return "GitHub'da değişiklik yapıyor (gh)"
    if name in _REMOTE_COMMANDS or (name == "rsync" and any(_is_remote(a) for a in arguments)):
        return f"uzak sunucuya bağlanıyor ({name})"
    if name in {"curl", "wget"} and _sends_data(name, arguments):
        return f"dışarıya veri gönderiyor ({name})"
    script = sub if name in _SCRIPT_RUNNERS else name
    if script.endswith(_SCRIPT_SUFFIXES) and is_outward_script(script):
        return f"dağıtım/yayın betiği ({script})"
    return None


def _remote_delete_verb(name: str, arguments: list[str]) -> str | None:
    """Uzak hesapta silen alt komut/fiil (`delete`, `terminate-instances`) ya da None."""
    if name not in _REMOTE_DELETERS:
        return None
    for argument in arguments[:_REMOTE_DELETE_SCAN]:
        if _REMOTE_DELETE_VERB.search(argument):
            return argument
    return None


def _gh_writes(arguments: list[str]) -> bool:
    """`gh …` GitHub'da bir şey değiştiriyor mu? `api` için salt-okur kapısının tersi."""
    if not arguments:
        return False
    if arguments[0] == "api":
        return not gh_reads_only(arguments)
    head = [argument for argument in arguments[:3] if not argument.startswith("-")]
    if any(argument in _GH_WRITES for argument in head[1:3]):
        return True
    return bool(head) and any(
        argument in _GH_COMMAND_WRITES.get(head[0], frozenset()) for argument in head[1:3]
    )


def _outward_run(arguments: list[str]) -> bool:
    """`npm run deploy` gibi adı dışa dönük iş söyleyen paket betiği mi?"""
    return len(arguments) >= 2 and arguments[0] == "run" and is_outward_script(arguments[1])


def _sends_data(name: str, arguments: list[str]) -> bool:
    if name == "wget":
        sends = any(
            a.startswith(("--post-data", "--post-file", "--method", "--body-data", "--body-file"))
            for a in arguments
        )
    else:
        sends = curl_sends_data(arguments)
    return sends and not only_local_urls(arguments)


def _is_remote(argument: str) -> bool:
    """rsync/scp hedefi `kullanıcı@sunucu:yol` ya da `sunucu:yol` mu?"""
    if argument.startswith(("-", "/", ".")):
        return False
    return re.match(r"^[\w.@-]+:", argument) is not None


def _reads_only(name: str, arguments: list[str]) -> bool:
    """Bu parça yalnız okuyor mu?"""
    if name == "git":
        return git_reads_only(arguments)
    if name == "sed":
        return sed_reads_only(arguments)
    if name == "awk":
        return awk_reads_only(arguments)
    if name == "find":
        return not any(a in _FIND_UNSAFE for a in arguments)
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
    """`python -c`, `node -e`, `php -r` gibi satır içi kodun metni.

    Yalnız YORUMLAYICILARDA: `grep -e os.remove src`, `sort -r`, `rm -r dizin` kod
    değildir (ölçüldü, 30 Ekim: alakasız onay sorusu üretiyordu).
    """
    if not (name.startswith("python") or name in _INTERPRETERS):
        return None
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
        prefix, parts = parts[0], parts[1:]
        parts = _drop_options(prefix, parts)
    if parts[:1] == ["xargs"]:
        parts = _drop_options("xargs", parts[1:])
    return parts


def _drop_options(prefix: str, parts: list[str]) -> list[str]:
    """Önek sözcüğün seçeneklerini (ve değerlerini) at: `env -u AD komut` → `komut`.

    Ölçüldü (29 Ekim): `env -i git push` ve `xargs -n 1 git push` seçenek/değer asıl
    komut sanıldığı için riskli komut görülmüyordu.
    """
    value_flags = _PREFIX_VALUE_FLAGS.get(prefix, frozenset())
    while parts and parts[0].startswith("-") and len(parts[0]) > 1:
        parts = parts[2:] if parts[0] in value_flags else parts[1:]
    return parts


def raw_segments(command: str) -> list[str]:
    """Zincirin ham alt komut metinleri (`_segments`; izin allow eşlemesi kullanır, #58)."""
    return _segments(command)


def _segments(command: str) -> list[str]:
    """Komutu `;`, `&&`, `||`, `|`, satır sonu ve alt kabuk (`$(…)`, ters tırnak) sınırlarından böl.

    Tırnak içi bölünmez: `python3 -c "a; b"` tek parçadır.
    """
    pieces: list[str] = []
    current: list[str] = []
    quote = ""
    escaped = False
    for char in command.replace("$(", "("):
        if escaped:
            # `\"` ve `\;` düz karakterdir: tırnak açmaz, komutu bölmez.
            current.append(char)
            escaped = False
            continue
        if char == "\\" and quote != "'":
            current.append(char)
            escaped = True
            continue
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


_QUOTED_OR_ESCAPED = re.compile(r"'[^']*'|\"(?:\\.|[^\"\\])*\"|\\.", re.DOTALL)


def _unquoted(command: str) -> str:
    """Tırnak içini boşaltılmış komut: `grep ">" a` içindeki `>` yönlendirme değildir.

    Ters eğik çizgiyle kaçırılmış karakter (tırnak, `>`) düz harftir; tırnak açmaz.
    """
    return _QUOTED_OR_ESCAPED.sub(
        lambda match: "_" if match.group(0).startswith("\\") else "''", command
    )
