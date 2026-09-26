"""Bir kabuk komutunun GÖZETİMSİZ çalışmaya uygun olup olmadığı.

Bu modül kara liste DEĞİLDİR. `safety.DANGER_RULES` tanıdığı yıkıcı kalıpları
yakalar ve yakalayamadığı her şeyi otomatik onaya bırakırdı; `node -e`, `perl -e`,
önceden yazılmış bir script, `>` ile dosya sıfırlama ya da `curl` ile veri
gönderme hiçbir kalıba uymadan geçebiliyordu. Kara listeye bir kalıp daha eklemek
bir sonraki kaçış yolunu kapatmaz.

Buradaki karar terstir: yalnızca TANIDIĞIMIZ ve yan etkisi olmayan komutlar
onaysız çalışır, kalan her şey kullanıcıya sorulur. Yanlış tarafa düşmenin
bedeli asimetriktir — gereksiz bir onay istemi kullanıcıyı yorar, atlanan bir
onay veri kaybettirir.

Bu bir kum havuzu (sandbox) DEĞİLDİR. Onay verildikten sonra komut yine kullanıcı
ortamında tam yetkiyle çalışır; burada karar verilen tek şey SORULUP sorulmayacağıdır.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from .command_paths import escapes_project
from .inline_python import is_inert_python

#: Yan etkisi olmayan, yalnızca okuyan/gösteren komutlar.
#:
#: `env` ve `printenv` bilinçli olarak YOK: argümansız çağrıldıklarında ortamı —
#: API anahtarları dahil — modele döker; `env sh -c "..."` ise ARDINDAKİ komutu
#: çalıştırır ve okuyucu kılığında her şeyi geçirirdi.
_READ_ONLY = frozenset(
    {
        "ls", "dir", "pwd", "cat", "bat", "head", "tail", "wc", "file", "stat",
        "grep", "egrep", "fgrep", "rg", "ag", "find", "fd", "tree", "which", "type",
        "echo", "printf", "date", "whoami", "hostname", "uname",
        "diff", "cmp", "sort", "uniq", "cut", "awk", "sed", "jq", "column",
        "du", "df", "ps", "top", "uptime", "id", "groups", "basename", "dirname",
        "realpath", "readlink", "true", "false", "test", "sleep",
    }
)  # fmt: skip

#: Yalnızca sürüm/yardım sorgusu için geçilen çalıştırıcılar. Bunlar keyfi kod
#: çalıştırabildiği için ancak zararsız bayraklarla ya da PROJE İÇİ bir dosyayla
#: (bkz. `_script_safe`) güvenli sayılır.
_VERSION_ONLY = frozenset({"python", "python3", "pip", "node", "npm", "go", "cargo"})
_VERSION_FLAGS = frozenset({"--version", "-V", "--help", "-h", "version"})

#: Proje içi bir betiği çalıştırabilen yorumlayıcılar.
#
# Agent'ın doğal akışı düzenle → çalıştır → doğrula. `python main.py` reddedilince
# agent görevi yarıda bırakıp kullanıcıya soruyor; headless bağlamda bu doğrudan
# başarısızlık (ölçüldü: çok dosyalı yeniden adlandırma görevi bu yüzden düşüyordu).
#
# Sınır şu: projedeki bir DOSYAYI çalıştırmak `pytest` çalıştırmakla aynı güven
# seviyesidir — ikisi de projenin kendi kodudur. Satır içi kod ENJEKTE etmek
# (`-c`, `-e`) ya da kök dışındaki bir betiği çalıştırmak farklıdır ve sorulur.
_SCRIPT_RUNNERS = frozenset({"python", "python3", "node"})

#: Satır içi kod alan bayraklar — proje dosyası çalıştırmakla aynı şey değildir.
#
# `-m` bu listede DEĞİLDİR ve bu bilinçlidir. `-m` toptan yasaklıyken kendi araç
# talimatımızın kanonik örneği (`python3 -m pytest -q`) onaysız geçemiyordu: modele
# çalıştırmasını söylediğimiz komut, etkileşimsiz ortamda reddediliyor ve agent
# tıkanıyordu. `python -m pytest`, `pytest` ile AYNI güven seviyesidir.
#
# Yasak yerine allowlist: yalnızca TANINAN kalite/test modülleri `-m` ile geçer.
# `python -m pip install` ya da `python -m http.server` geçmez.
_INLINE_CODE_FLAGS = frozenset({"-c", "-e", "--eval"})

#: `-m` ile onaysız çalıştırılabilen modüller. Hepsi projenin kendi kodunu
#: denetleyen/çalıştıran araçlardır; `_DIRECT_TOOLING` ile aynı gerekçe.
_MODULE_RUNNERS = frozenset(
    {"pytest", "unittest", "ruff", "mypy", "tox", "compileall", "venv", "black", "isort"}
)

#: Projenin kendi kalite araçları. Bunlar projede TANIMLI kodu çalıştırır (test
#: dosyaları, lint eklentileri) — yani teknik olarak keyfi kod yürütürler.
#:
#: Yine de onaysız geçerler ve bu bilinçli bir tavizdir: kullanıcı bu projeyi
#: zaten açtı, doğrulama kapısı (`/verify`) aynı komutları her turdan sonra
#: çalıştırıyor ve her `pytest` için onay istemek auto kipini kullanılamaz hale
#: getirirdi. Sınır şudur: araç TANINAN bir kalite aracı olmalı ve komut proje
#: kökünde çalışmalı; `npm run <script>` gibi projeye özgü tanımlar da buraya
#: girer çünkü içeriğini projenin sahibi yazmıştır.
_PROJECT_TOOLING = frozenset(
    {
        "pytest", "ruff", "mypy", "tox", "eslint", "tsc", "vitest", "jest",
        "make", "cargo", "go", "npm", "pnpm", "yarn", "bun",
    }
)  # fmt: skip

#: Alt komut ALMAYAN kalite araçları — çağrıldıklarında zaten yalnızca denetim yapar.
_DIRECT_TOOLING = frozenset({"pytest", "ruff", "mypy", "tox", "eslint", "tsc", "vitest", "jest"})

#: Proje aracının onaysız geçebileceği alt komutlar. `npm install` (ağdan paket
#: çeker) ya da `cargo publish` (yayınlar) buraya girmez.
_TOOLING_SUBCOMMANDS = frozenset(
    {"test", "check", "lint", "typecheck", "run", "fmt", "format", "build", "vet"}
)

#: Oyun motorunun BAŞSIZ doğrulama çağrısında onaysız geçen bayraklar.
#:
#: Ölçüldü (canlı Godot koşusu): plan son adımda `godot --headless --path . --quit`
#: çalıştırmak istedi, komut tanınmadığı için onay istendi ve etkileşimsiz oturumda
#: reddedildi — oyun hiçbir zaman doğrulanamadı. Aynı komutu proje kapısı
#: (`verify_discovery._godot`) zaten her turda onaysız çalıştırıyor; gevşetme yeni
#: bir yetki açmaz, iki yolu aynı güven seviyesine getirir.
#:
#: Sınır dar tutulur: `--headless` ZORUNLUDUR ve yalnız aşağıdaki bayraklar geçer.
#: Dışa aktarma (`--export-*`), betik çalıştırma (`--script`) ya da başsız olmayan
#: çağrı onay ister.
#: `--editor`, projeyi kurulum aşamasında AÇIP kapatan kapının bayrağıdır: ölçüldü,
#: ana sahne tanımlanmadan `--quit` ve `--quit-after` dönmüyor, `--editor --quit`
#: sıfır çıkışla dönüyor. İçe aktarma önbelleği yazar, projeyi değiştirmez.
_GODOT_VERIFY_FLAGS = frozenset(
    {"--headless", "--path", "--quit", "--quit-after", "--verbose", "--editor"}
)

#: Proje içindeki dosya/klasörü değiştiren komutlar (Claude'un otomatik kipi gibi).
#:
#: Ölçüldü (26 Eylül): auto kip `mkdir`, `touch`, `cp`, `mv` için bile soruyordu;
#: aynı işi `write_file` aracı zaten sormadan yapıyor. Proje dışına çıkan yol
#: `escapes_project` ile önce elenir; `rm -rf` gibi yıkıcı kalıplar
#: `safety.danger_reason` ile ayrıca sorulur.
_WORKSPACE_MUTATORS = frozenset({"mkdir", "touch", "cp", "mv", "rm", "ln", "rmdir"})

#: Kod biçimlendiriciler: yalnız proje dosyalarını yeniden yazar.
_FORMATTERS = frozenset({"prettier", "black", "isort", "gofmt", "rustfmt", "biome", "autopep8"})

#: Paket yöneticilerinin proje içine kuran alt komutları. Global kurulum
#: (`-g`, `--global`, `--user`) ve yayımlama sorulur.
_JS_INSTALL_SUBCOMMANDS = frozenset(
    {"install", "i", "add", "ci", "remove", "uninstall", "rm", "update", "up"}
)
_GLOBAL_INSTALL_FLAGS = frozenset(
    {"-g", "--global", "--user", "--system", "--break-system-packages"}
)

#: Projenin kendi betiğini çalıştıran kabuklar (`bash kurulum.sh`).
_SHELL_RUNNERS = frozenset({"bash", "sh", "zsh"})

#: `curl`'ü okuyucu olmaktan çıkaran, veri GÖNDEREN bayraklar.
_CURL_SEND_FLAGS = frozenset(
    {"-d", "--data", "--data-raw", "--data-binary", "--data-urlencode", "-F", "--form",
     "-T", "--upload-file", "-X", "--request", "-K", "--config"}
)  # fmt: skip

#: Otomatik kipte onaysız geçen, YEREL etkili git alt komutları. Uzak depoya
#: yazan (`push`), geçmişi yeniden yazan (`rebase`) ve kaydedilmemiş işi silen
#: (`reset --hard`, `clean`) komutlar burada yoktur.
_LOCAL_GIT_SUBCOMMANDS = frozenset(
    {
        "add",
        "commit",
        "checkout",
        "switch",
        "restore",
        "stash",
        "init",
        "mv",
        "rm",
        "fetch",
        "reset",
    }
)
_GIT_DESTRUCTIVE_FLAGS = frozenset({"--hard", "--force", "-f", "--amend"})

#: Onaysız geçilen git alt komutları — TEK KAYNAK.
#:
#: Git iki ayrı yoldan gelebilir (`git` aracı ve `run_shell`) ve ikisinde de aynı
#: kararın verilmesi gerekir. Liste eskiden `shell.py` içinde ikinci kez yazılıydı;
#: iki kopya zamanla ayrışıp aynı komutun bir yoldan onaysız, öteki yoldan onaylı
#: geçmesine yol açabilirdi. `shell` bu listeyi buradan alır.
READONLY_GIT_SUBCOMMANDS = frozenset(
    {
        "status",
        "diff",
        "log",
        "show",
        "branch",
        "ls-files",
        "blame",
        "remote",
        "tag",
        "rev-parse",
        "ls-remote",
        "symbolic-ref",
        "rev-list",
    }
)

#: Komutu parçalara bölen iki karakterlik kabuk operatörleri. Zincirin HER parçası
#: güvenli olmalı: `ls && rm -rf build` ilk parçasına bakılarak geçirilemez.
_DOUBLE_SEPARATORS = ("&&", "||")
_SINGLE_SEPARATORS = frozenset({"|", ";", "\n"})

#: Tırnak DIŞINDA görüldüğünde komutu belirsiz kılan metakarakterler: yönlendirme
#: dosyayı sıfırlar, `&` arka plana atar. Tırnak içindeki `>` düz metindir
#: (`grep ">" a.txt`, `python3 -c "print(1 > 0)"`) ve sayılmaz.
_UNQUOTED_UNSAFE = frozenset({">", "<", "&"})

#: Çift tırnak İÇİNDE de açılan ikameler: `ls "$(rm -rf /)"` içindeki asıl komut
#: gizlidir ve beyaz listeyi anlamsız kılar. Yalnız tek tırnak bunları durdurur.
_EXPANSIONS = ("$(", "${", "`")

#: `find` için silme/çalıştırma bayrakları — komutun kendisi okuyucu olsa da bunlar
#: onu yıkıcı yapar.
_FIND_UNSAFE = frozenset({"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fls", "-fprint"})


def is_unattended_safe(command: str, root: Path | None = None) -> bool:
    """Komut, kullanıcıya sorulmadan çalıştırılabilir mi?

    False dönmek "bu komut zararlı" demek DEĞİLDİR; "tanımıyorum, sorulmalı"
    demektir. Varsayılan cevap budur.
    """
    if not command.strip():
        return False
    segments = _split(command, root)
    if segments is None:
        return False
    return all(_segment_safe(segment, root) for segment in segments)


def _split(command: str, root: Path | None = None) -> list[str] | None:
    """Komutu tırnaklara saygı göstererek zincir parçalarına böl.

    Düz `str.split` tırnak içini de bölüyordu: `python3 -c "import sys; print(1)"`
    noktalı virgülden ikiye ayrılıyor, kapanmamış tırnak yüzünden onaya düşüyordu.
    Kabuğun yorumlayacağı bir yönlendirme/ikame görülürse None döner (sorulur).
    """
    segments: list[str] = []
    current: list[str] = []
    quote = ""
    index = 0
    while index < len(command):
        char, pair = command[index], command[index : index + 2]
        step = 1
        if quote == "'":
            quote = "" if char == "'" else quote
        elif char == "\\":
            step = 2
        elif pair.startswith(_EXPANSIONS):
            return None
        elif quote:
            quote = "" if char == quote else quote
        elif char in "'\"":
            quote = char
        elif pair in _DOUBLE_SEPARATORS or char in _SINGLE_SEPARATORS:
            segments.append("".join(current))
            current = []
            index += len(pair) if pair in _DOUBLE_SEPARATORS else 1
            continue
        elif char == "&" and command[index + 1 : index + 2] in {"", " ", "\n", "\t"}:
            # Sondaki `&` komutu arka plana atar (`python3 app.py &`): sunucuyu
            # başlatıp sınamak doğal akıştır; parçalar yine ayrı ayrı denetlenir.
            segments.append("".join(current))
            current = []
            index += 1
            continue
        elif char == ">" or (char == "&" and command[index + 1 : index + 2] == ">"):
            atla = _safe_redirect_length(command, index, root)
            if atla is None:
                return None
            index += atla
            continue
        elif char in _UNQUOTED_UNSAFE:
            return None
        current.append(command[index : index + step])
        index += step
    segments.append("".join(current))
    return [segment.strip() for segment in segments if segment.strip()]


def _safe_redirect_length(command: str, index: int, root: Path | None = None) -> int | None:
    """`>`, `>>`, `&>`, `2>&1` yönlendirmesi proje İÇİNE mi yazıyor?

    Hedef göreli ve kökten çıkmayan bir yol, `/dev/null` ya da başka bir
    tanımlayıcı (`&1`) olmalıdır; aksi hâlde komut sorulur. Dönüş, komut
    metninde atlanacak karakter sayısıdır (yönlendirme + hedef).
    """
    cursor = index
    if command[cursor] == "&":
        cursor += 1
    cursor += 1  # '>'
    if command[cursor : cursor + 1] == ">":
        cursor += 1
    if command[cursor : cursor + 1] == "&":
        cursor += 1
        start = cursor
        while cursor < len(command) and command[cursor].isdigit():
            cursor += 1
        return cursor - index if cursor > start else None
    while cursor < len(command) and command[cursor] == " ":
        cursor += 1
    start = cursor
    while cursor < len(command) and command[cursor] not in " ;|&\n":
        cursor += 1
    target = command[start:cursor]
    if not target or any(char in target for char in "$`'\""):
        return None
    if target != "/dev/null" and escapes_project("cat", [target], root):
        return None
    return cursor - index


def _segment_safe(segment: str, root: Path | None = None) -> bool:
    try:
        parts = shlex.split(segment)
    except ValueError:
        # Kapanmamış tırnak: komutun ne yapacağı belirsiz. Şüphede kalırsan sor.
        return False
    if not parts:
        return False

    # `2>&1` yönlendirmesinden geriye kalan tanımlayıcı rakamı argüman değildir.
    if len(parts) > 1 and parts[-1].isdigit() and segment.rstrip().endswith(" " + parts[-1]):
        parts = parts[:-1]
    if parts[0] == "sudo":
        return False
    name = parts[0].rsplit("/", 1)[-1]
    arguments = parts[1:]
    # `./run.sh`: projenin kendi betiği, `pytest` ile aynı güven seviyesi.
    # Adı dışa dönük iş söyleyen betik (deploy/publish/release/push) sorulur.
    if parts[0].startswith("./") and not escapes_project("cat", [parts[0]], root):
        return not _outward_script(name) and not escapes_project(name, arguments, root)

    # Salt-okur komut da proje dışını okuyabilir (`cat ~/.ssh/id_rsa`): önce NEREYE
    # dokunduğuna bakılır, sonra komutun kendisine.
    if escapes_project(name, arguments, root):
        return False
    if name == "git":
        return _git_safe(arguments)
    if name == "cd":
        return len(arguments) <= 1
    if name in {"rm", "rmdir"}:
        # Özyinelemeli/zorlamalı silme her zaman sorulur (bkz. `safety`).
        ozyinelemeli = any(a.startswith("-") and "r" in a.lower() for a in arguments)
        jokerli = any(char in a for a in arguments for char in "*?")
        return not ozyinelemeli and not jokerli
    if name in _WORKSPACE_MUTATORS or name in _FORMATTERS:
        return True
    if name == "chmod":
        return not any(argument.startswith("-R") for argument in arguments)
    if name in _SHELL_RUNNERS:
        return (
            bool(arguments)
            and not arguments[0].startswith("-")
            and not _outward_script(arguments[0])
        )
    if name in {"npx", "bunx"}:
        return bool(arguments) and not any(a in _INLINE_CODE_FLAGS for a in arguments)
    if name in {"pip", "pip3"} or (name == "uv" and arguments[:1] == ["pip"]):
        return _pip_safe(arguments[1:] if name == "uv" else arguments)
    if name == "curl":
        sends = any(
            argument in _CURL_SEND_FLAGS or argument.startswith(("--data", "-d@"))
            for argument in arguments
        )
        # Kendi yerel sunucusunu sınamak (`curl -X POST localhost:5000/...`) dışa
        # veri göndermek değildir; Claude'un otomatik kipi de bunu sormaz.
        return not sends or _only_local_urls(arguments)
    if name in {"source", "."}:
        # Proje içindeki sanal ortamı etkinleştirmek; kök dışı yol yukarıda elendi.
        return len(arguments) == 1
    if name == "open":
        return bool(arguments) and not arguments[0].startswith("-")
    if name == "find":
        return not any(argument in _FIND_UNSAFE for argument in arguments)
    if name in _PROJECT_TOOLING:
        return _tooling_safe(name, arguments)
    if name == "godot":
        return _godot_verify_safe(arguments)
    if name in _VERSION_ONLY:
        if all(argument in _VERSION_FLAGS for argument in arguments) and arguments:
            return True
        return name in _SCRIPT_RUNNERS and _script_safe(name, arguments)
    return name in _READ_ONLY


def _godot_verify_safe(arguments: list[str]) -> bool:
    """Godot çağrısı yalnız BAŞSIZ doğrulama mı yapıyor?

    Bayrak dışı değerlere (`--path .`, `--quit-after 180`) izin verilir; tanınmayan
    bir bayrak görüldüğü anda komut onaya düşer.
    """
    if "--headless" not in arguments:
        return False
    return all(
        argument in _GODOT_VERIFY_FLAGS for argument in arguments if argument.startswith("-")
    )


def _script_safe(name: str, arguments: list[str]) -> bool:
    """Yorumlayıcı çağrısı PROJE İÇİ bir dosyayı mı çalıştırıyor?

    İlk argüman göreli bir yol olmalı; kökün dışına çıkan yol (mutlak, `..`, `~`)
    `_segment_safe` içinde zaten elenmiştir. Satır içi kod bayrakları reddedilir —
    `python -c "..."` yeni kod enjekte etmektir — TEK istisna, ayrıştırılıp yalnız
    bilgi yazdırdığı kanıtlanan Python kodudur (`inline_python`).
    """
    if not arguments:
        return False
    if name.startswith("python") and len(arguments) == 2 and arguments[0] == "-c":
        return is_inert_python(arguments[1])
    if any(argument in _INLINE_CODE_FLAGS for argument in arguments):
        return False
    if arguments[0] == "-m":
        # `python -m <modül>`: yalnızca tanınan kalite/test modülleri onaysız geçer.
        if arguments[1:2] == ["pip"]:
            return _pip_safe(arguments[2:])
        return len(arguments) > 1 and arguments[1].split(".")[0] in _MODULE_RUNNERS
    return not arguments[0].startswith("-")


def _tooling_safe(name: str, arguments: list[str]) -> bool:
    """Proje aracı onaysız geçebilir mi?

    Alt komut alan araçlarda (`npm`, `cargo`, `go`, `make`) yalnızca kalite/test
    alt komutları geçer: `npm install` ağdan paket çeker, `cargo publish` yayınlar
    ve ikisi de geri alınamaz sonuçlar doğurur.
    """
    if name in _DIRECT_TOOLING:
        return True
    if not arguments:
        return name in {"npm", "pnpm", "yarn", "bun", "make"} and name != "npm"
    if name in {"npm", "pnpm", "yarn", "bun"} and arguments[0] in _JS_INSTALL_SUBCOMMANDS:
        return not any(argument in _GLOBAL_INSTALL_FLAGS for argument in arguments)
    if name == "pnpm" and arguments[0] == "dlx":
        return True
    return arguments[0] in _TOOLING_SUBCOMMANDS


_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "[::1]", "::1"})


def _only_local_urls(arguments: list[str]) -> bool:
    """Komuttaki bütün adresler bu makineye mi gidiyor? Adres yoksa False."""
    from urllib.parse import urlsplit

    urls = [a for a in arguments if "://" in a or a.startswith(tuple(_LOCAL_HOSTS))]
    if not urls:
        return False
    for url in urls:
        host = urlsplit(url if "://" in url else f"http://{url}").hostname or ""
        if host not in _LOCAL_HOSTS and f"[{host}]" not in _LOCAL_HOSTS:
            return False
    return True


def _outward_script(path: str) -> bool:
    """Betiğin adı dışa dönük bir iş mi söylüyor? (dağıtım, yayımlama, gönderme)"""
    ad = path.rsplit("/", 1)[-1].lower()
    return any(kelime in ad for kelime in ("deploy", "publish", "release", "push", "upload"))


def _pip_safe(arguments: list[str]) -> bool:
    """`pip install …` proje ortamına mı kuruyor? Global/kullanıcı kurulumu sorulur."""
    if not arguments or arguments[0] not in {"install", "uninstall"}:
        return False
    return not any(argument in _GLOBAL_INSTALL_FLAGS for argument in arguments)


def _git_safe(arguments: list[str]) -> bool:
    """Salt-okur ya da YEREL etkili git komutu mu? Push/rebase/clean/--hard sorulur."""
    if not arguments:
        return False
    if arguments[0] in READONLY_GIT_SUBCOMMANDS:
        return True
    if arguments[0] not in _LOCAL_GIT_SUBCOMMANDS:
        return False
    return not any(argument in _GIT_DESTRUCTIVE_FLAGS for argument in arguments[1:])
