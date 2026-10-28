"""Okuyucu adı taşıyan komutun gerçekten yalnız okuyup okumadığı.

`awk`, `sed` ve `git branch` adları okuyucu gibi görünür ama argümanlarıyla
komut çalıştırabilir, dosya yazabilir ya da dal silebilir. Ölçüldü (28 Ekim):
`awk 'BEGIN {system(...)}'`, `sed 'w dosya'` ve `git branch -D x` salt-okur
sayılıyordu. Buradaki denetimler programı/argümanları okur; emin olunamayan her
durum "salt-okur değil" sayılır (gereksiz bir onay, atlanan bir onaydan ucuzdur).

Bu bir kum havuzu değildir; yalnız sorulup sorulmayacağına karar verir.
"""

from __future__ import annotations

import re

#: Alt komut adına göre salt-okur olabilecek git komutları — TEK KAYNAK.
#: Argümanlar ayrıca `git_reads_only` ile denetlenir: `branch -D` bu adı taşır.
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

# --- awk -------------------------------------------------------------------

#: Programı dosyadan alan, dosyayı yerinde değiştiren veya eklenti yükleyen bayraklar.
_AWK_UNSAFE_FLAGS = ("-f", "--file", "-i", "--include", "-E", "--exec", "-l", "--load")
#: Değer alan bayraklar (`-F :`, `-v ad=değer`); değerleri program sayılmaz.
_AWK_VALUE_FLAGS = frozenset({"-F", "-v", "--field-separator", "--assign"})
_AWK_STRING = re.compile(r'"(?:\\.|[^"\\])*"')
_AWK_REGEX = re.compile(r"/(?:\\.|[^/\\\n])*/")
_AWK_SYSTEM = re.compile(r"\bsystem\s*\(")
_AWK_PIPE = re.compile(r"(?<!\|)\|(?!\|)")
_AWK_REDIRECT = re.compile(r"\bprintf?\b[^;{}]*?>")


def awk_reads_only(arguments: list[str]) -> bool:
    """awk programı komut çalıştırmıyor, boruya ya da dosyaya yazmıyor mu?"""
    program: str | None = None
    skip_value = False
    for argument in arguments:
        if skip_value:
            skip_value = False
            continue
        if argument.startswith(_AWK_UNSAFE_FLAGS):
            return False
        if argument in _AWK_VALUE_FLAGS:
            skip_value = True
            continue
        if argument.startswith("-"):
            continue
        program = argument
        break
    if program is None:
        return False
    # Dizgi ve düzenli ifade gövdeleri (`/hata|uyarı/`) boru/yönlendirme değildir.
    code = _AWK_REGEX.sub(" ", _AWK_STRING.sub('""', program))
    return not (_AWK_SYSTEM.search(code) or _AWK_PIPE.search(code) or _AWK_REDIRECT.search(code))


# --- sed -------------------------------------------------------------------

_SED_UNSAFE_FLAGS = ("-i", "--in-place", "-f", "--file")
_SED_EXPRESSION_FLAGS = frozenset({"-e", "--expression"})
#: `s/eski/yeni/bayraklar` — `w dosya` ve `e` bayrakları yazar/çalıştırır.
_SED_SUBSTITUTE = re.compile(
    r"s([^\w\s\\])(?:\\.|(?!\1).)*\1(?:\\.|(?!\1).)*\1([A-Za-z0-9]*)", re.DOTALL
)
_SED_TRANSLITERATE = re.compile(r"y([^\w\s\\])(?:\\.|(?!\1).)*\1(?:\\.|(?!\1).)*\1", re.DOTALL)
_SED_ADDRESS = re.compile(r"/(?:\\.|[^/\\\n])*/")
#: Komut konumundaki `w`/`W` (dosyaya yaz) ve `e` (kabukta çalıştır).
_SED_WRITE_COMMAND = re.compile(r"(?:^|[;{}\s\d$!,])[wWe]")


def sed_reads_only(arguments: list[str]) -> bool:
    """sed betiği dosyayı yerinde değiştirmiyor, dosyaya yazmıyor, komut çalıştırmıyor mu?"""
    scripts: list[str] = []
    expression_next = False
    for argument in arguments:
        if expression_next:
            scripts.append(argument)
            expression_next = False
            continue
        if argument.startswith(_SED_UNSAFE_FLAGS):
            return False
        if argument in _SED_EXPRESSION_FLAGS:
            expression_next = True
            continue
        if argument.startswith("--expression="):
            scripts.append(argument.split("=", 1)[1])
            continue
        if argument.startswith("-"):
            continue
        if not scripts:
            scripts.append(argument)
        # İlk betikten sonraki konumsal argümanlar okunacak dosyalardır.
    return bool(scripts) and not any(_sed_script_writes(script) for script in scripts)


def _sed_script_writes(script: str) -> bool:
    for match in _SED_SUBSTITUTE.finditer(script):
        if set(match.group(2)) & {"w", "W", "e"}:
            return True
    rest = _SED_SUBSTITUTE.sub(" ", script)
    rest = _SED_TRANSLITERATE.sub(" ", rest)
    rest = _SED_ADDRESS.sub(" ", rest)
    return _SED_WRITE_COMMAND.search(rest) is not None


# --- git -------------------------------------------------------------------

_BRANCH_MUTATING = frozenset(
    {"-d", "-D", "--delete", "-m", "-M", "--move", "-c", "-C", "--copy", "-f", "--force",
     "-u", "--unset-upstream", "--edit-description", "-t", "--track", "--no-track"}
)  # fmt: skip
_TAG_MUTATING = frozenset(
    {"-d", "--delete", "-a", "--annotate", "-s", "--sign", "-f", "--force", "-m",
     "--message", "-F", "--file", "-u", "--local-user", "-e", "--edit"}
)  # fmt: skip
#: Konumsal argümanı ad OLUŞTURMAK yerine süzgeç yapan listeleme bayrakları.
_LISTING_FLAGS = frozenset(
    {"-l", "--list", "--contains", "--no-contains", "--merged", "--no-merged", "--points-at"}
)
_REMOTE_READS = frozenset({"-v", "--verbose", "show", "get-url"})


def git_reads_only(arguments: list[str]) -> bool:
    """git çağrısı depoda/dosyada hiçbir şey değiştirmiyor mu?"""
    if not arguments or arguments[0] not in READONLY_GIT_SUBCOMMANDS:
        return False
    sub, rest = arguments[0], arguments[1:]
    if any(argument.startswith("--output") for argument in rest):
        return False
    if sub == "branch":
        return _ref_listing_only(rest, _BRANCH_MUTATING, ("--set-upstream-to", "--track="))
    if sub == "tag":
        return _ref_listing_only(rest, _TAG_MUTATING, ("--message=", "--file="))
    if sub == "remote":
        return not rest or rest[0] in _REMOTE_READS
    if sub == "symbolic-ref":
        positional = [argument for argument in rest if not argument.startswith("-")]
        return len(positional) <= 1 and not {"-d", "--delete"} & set(rest)
    return True


def _ref_listing_only(
    rest: list[str], mutating: frozenset[str], mutating_prefixes: tuple[str, ...]
) -> bool:
    """`branch`/`tag` yalnız listeliyor mu? Konumsal ad, listeleme bayrağı olmadan oluşturur."""
    if any(argument in mutating or argument.startswith(mutating_prefixes) for argument in rest):
        return False
    positional = [argument for argument in rest if not argument.startswith("-")]
    return not positional or bool(_LISTING_FLAGS & set(rest))
