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

#: Yan etkisi olmayan, yalnızca okuyan/gösteren komutlar.
_READ_ONLY = frozenset(
    {
        "ls", "dir", "pwd", "cat", "bat", "head", "tail", "wc", "file", "stat",
        "grep", "egrep", "fgrep", "rg", "ag", "find", "fd", "tree", "which", "type",
        "echo", "printf", "date", "whoami", "hostname", "uname", "env", "printenv",
        "diff", "cmp", "sort", "uniq", "cut", "awk", "sed", "jq", "column",
        "du", "df", "ps", "top", "uptime", "id", "groups", "basename", "dirname",
        "realpath", "readlink", "true", "false", "test",
    }
)  # fmt: skip

#: Yalnızca sürüm/yardım sorgusu için geçilen çalıştırıcılar. Bunlar keyfi kod
#: çalıştırabildiği için ancak zararsız bayraklarla güvenli sayılır.
_VERSION_ONLY = frozenset({"python", "python3", "pip", "node", "npm", "go", "cargo"})
_VERSION_FLAGS = frozenset({"--version", "-V", "--help", "-h", "version"})

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

#: Onaysız geçilen git alt komutları. `shell.READONLY_GIT_SUBCOMMANDS` ile aynı
#: listedir; git iki ayrı yoldan (git aracı ve run_shell) gelebildiği için karar
#: iki yerde de aynı olmalıdır.
_READONLY_GIT = frozenset(
    {"status", "diff", "log", "show", "branch", "ls-files", "blame", "remote", "tag"}
)

#: Komutu parçalara bölen kabuk operatörleri. Zincirin HER parçası güvenli olmalı:
#: `ls && rm -rf build` ilk parçasına bakılarak geçirilemez.
_SEPARATORS = ("&&", "||", "|", ";", "\n")

#: Kabuk metakarakterleri: yönlendirme dosyayı sıfırlar, ikame beyaz listeyi
#: tamamen anlamsız kılar (`ls $(rm -rf /)` içindeki asıl komut gizlidir).
_UNSAFE_TOKENS = (">", "<", "$(", "`", "${", "&")

#: `find` için silme/çalıştırma bayrakları — komutun kendisi okuyucu olsa da bunlar
#: onu yıkıcı yapar.
_FIND_UNSAFE = frozenset({"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fls", "-fprint"})


def is_unattended_safe(command: str) -> bool:
    """Komut, kullanıcıya sorulmadan çalıştırılabilir mi?

    False dönmek "bu komut zararlı" demek DEĞİLDİR; "tanımıyorum, sorulmalı"
    demektir. Varsayılan cevap budur.
    """
    if not command.strip():
        return False
    if any(token in command for token in _UNSAFE_TOKENS):
        return False
    return all(_segment_safe(segment) for segment in _split(command))


def _split(command: str) -> list[str]:
    parcalar = [command]
    for separator in _SEPARATORS:
        parcalar = [alt for parca in parcalar for alt in parca.split(separator)]
    return [parca.strip() for parca in parcalar if parca.strip()]


def _segment_safe(segment: str) -> bool:
    try:
        parts = shlex.split(segment)
    except ValueError:
        # Kapanmamış tırnak: komutun ne yapacağı belirsiz. Şüphede kalırsan sor.
        return False
    if not parts:
        return False

    name = parts[0].rsplit("/", 1)[-1]
    arguments = parts[1:]

    if name == "git":
        return bool(arguments) and arguments[0] in _READONLY_GIT
    if name == "find":
        return not any(argument in _FIND_UNSAFE for argument in arguments)
    if name in _PROJECT_TOOLING:
        return _tooling_safe(name, arguments)
    if name in _VERSION_ONLY:
        return bool(arguments) and all(argument in _VERSION_FLAGS for argument in arguments)
    return name in _READ_ONLY


def _tooling_safe(name: str, arguments: list[str]) -> bool:
    """Proje aracı onaysız geçebilir mi?

    Alt komut alan araçlarda (`npm`, `cargo`, `go`, `make`) yalnızca kalite/test
    alt komutları geçer: `npm install` ağdan paket çeker, `cargo publish` yayınlar
    ve ikisi de geri alınamaz sonuçlar doğurur.
    """
    if name in _DIRECT_TOOLING:
        return True
    return bool(arguments) and arguments[0] in _TOOLING_SUBCOMMANDS
