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
_MODULE_RUNNERS = frozenset({"pytest", "unittest", "ruff", "mypy", "tox", "compileall"})

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

#: Onaysız geçilen git alt komutları — TEK KAYNAK.
#:
#: Git iki ayrı yoldan gelebilir (`git` aracı ve `run_shell`) ve ikisinde de aynı
#: kararın verilmesi gerekir. Liste eskiden `shell.py` içinde ikinci kez yazılıydı;
#: iki kopya zamanla ayrışıp aynı komutun bir yoldan onaysız, öteki yoldan onaylı
#: geçmesine yol açabilirdi. `shell` bu listeyi buradan alır.
READONLY_GIT_SUBCOMMANDS = frozenset(
    {
        "status", "diff", "log", "show", "branch", "ls-files", "blame", "remote",
        "tag", "rev-parse", "ls-remote", "symbolic-ref", "rev-list",
    }
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
        return bool(arguments) and arguments[0] in READONLY_GIT_SUBCOMMANDS
    if name == "find":
        return not any(argument in _FIND_UNSAFE for argument in arguments)
    if name in _PROJECT_TOOLING:
        return _tooling_safe(name, arguments)
    if name in _VERSION_ONLY:
        if all(argument in _VERSION_FLAGS for argument in arguments) and arguments:
            return True
        return name in _SCRIPT_RUNNERS and _script_safe(arguments)
    return name in _READ_ONLY


def _script_safe(arguments: list[str]) -> bool:
    """Yorumlayıcı çağrısı PROJE İÇİ bir dosyayı mı çalıştırıyor?

    İlk argüman göreli bir yol olmalı ve kökün dışına çıkmamalı. Mutlak yol, `..`
    ve `~` reddedilir: bunlar projenin kodu değildir. Satır içi kod bayrakları da
    reddedilir — `python -c "..."` yeni kod enjekte etmektir, var olan bir dosyayı
    çalıştırmak değil.
    """
    if not arguments:
        return False
    if any(argument in _INLINE_CODE_FLAGS for argument in arguments):
        return False
    if arguments[0] == "-m":
        # `python -m <modül>`: yalnızca tanınan kalite/test modülleri onaysız geçer.
        return len(arguments) > 1 and arguments[1].split(".")[0] in _MODULE_RUNNERS
    hedef = arguments[0]
    return not (hedef.startswith(("-", "/", "~")) or ".." in hedef.split("/"))


def _tooling_safe(name: str, arguments: list[str]) -> bool:
    """Proje aracı onaysız geçebilir mi?

    Alt komut alan araçlarda (`npm`, `cargo`, `go`, `make`) yalnızca kalite/test
    alt komutları geçer: `npm install` ağdan paket çeker, `cargo publish` yayınlar
    ve ikisi de geri alınamaz sonuçlar doğurur.
    """
    if name in _DIRECT_TOOLING:
        return True
    return bool(arguments) and arguments[0] in _TOOLING_SUBCOMMANDS
