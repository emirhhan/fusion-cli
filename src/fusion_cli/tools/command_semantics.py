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

#: Değer alan, programı değiştirmeyen bayraklar (`-F :`, `-v ad=değer`). Bunların
#: DIŞINDAKİ her bayrak (`-f`, `-e`/`--source`, `-i inplace`, `-l`) sorulur.
_AWK_VALUE_FLAGS = frozenset({"-F", "-v", "--field-separator", "--assign"})
_AWK_ATTACHED_VALUE = ("-F", "-v", "--field-separator=", "--assign=")
_AWK_STRING = re.compile(r'"(?:\\.|[^"\\])*"')
#: Komut çalıştıran ya da dışarı yazan yapılar. Düzenli ifadeler SIYRILMAZ: `/`
#: bölme işareti de olabilir ve sıyırma `4/2; system(...); 1/1` gibi kodu gizler.
#: `/a|b/` gibi bir desen bu yüzden onaya düşer; gereksiz onay kabul edilir.
_AWK_UNSAFE_CODE = re.compile(r"\bsystem\b|\bgetline\b|@|(?<!\|)\|(?!\|)")
_AWK_REDIRECT = re.compile(r"\bprintf?\b[^;{}]*?>")


def awk_reads_only(arguments: list[str]) -> bool:
    """awk programı komut çalıştırmıyor, boruya ya da dosyaya yazmıyor mu?"""
    program: str | None = None
    skip_value = False
    for argument in arguments:
        if skip_value:
            skip_value = False
            continue
        if argument in _AWK_VALUE_FLAGS:
            skip_value = True
            continue
        if argument.startswith(_AWK_ATTACHED_VALUE):
            continue
        if argument.startswith("-"):
            return False
        program = argument
        break
    if program is None or skip_value:
        return False
    # Dizgi içindeki `|` ya da `>` düz metindir; tırnaklar kalır, içerik boşalır.
    code = _AWK_STRING.sub('""', program)
    return not (_AWK_UNSAFE_CODE.search(code) or _AWK_REDIRECT.search(code))


# --- sed -------------------------------------------------------------------

#: Yalnız okuma davranışını değiştiren kısa ve uzun bayraklar. Listede olmayan her
#: bayrak (`-i`, `-f`, `--in-pl` kısaltması, `-ni` kümesi) sorulur.
_SED_SAFE_SHORT = frozenset("nErsuz")
_SED_SAFE_LONG = frozenset(
    {"--quiet", "--silent", "--regexp-extended", "--separate", "--null-data",
     "--unbuffered", "--posix", "--debug", "--sandbox"}
)  # fmt: skip
#: `s/eski/yeni/bayraklar`; izin verilen bayraklar dışındakiler (`w`, `e`) sorulur.
_SED_SUBSTITUTE = re.compile(
    r"s([^\w\s\\])(?:\\.|(?!\1).)*\1(?:\\.|(?!\1).)*\1([A-Za-z0-9]*)", re.DOTALL
)
_SED_SAFE_SUBSTITUTE_FLAGS = frozenset("gpiImM0123456789")
_SED_TRANSLITERATE = re.compile(r"y([^\w\s\\])(?:\\.|(?!\1).)*\1(?:\\.|(?!\1).)*\1", re.DOTALL)
#: `/desen/` ve `\cdesenc` adresleri, ardından `I`/`M` bayrakları.
_SED_ADDRESS = re.compile(r"(?:/(?:\\.|[^/\\\n])*/|\\([^\\\n])(?:\\.|(?!\1).)*\1)[IM]*")
#: Adresler ve s/y çıkarıldıktan sonra kalabilecek, yalnız okuyan komutlar.
_SED_READ_ONLY_REST = re.compile(r"^[\s\d$,;{}!~+=pdqQnNlPDhHgGxz]*$")


def sed_reads_only(arguments: list[str]) -> bool:
    """sed dosyayı yerinde değiştirmiyor, dosyaya yazmıyor, komut çalıştırmıyor mu?"""
    scripts: list[str] = []
    has_expression = False
    expression_next = False
    for argument in arguments:
        if expression_next:
            scripts.append(argument)
            expression_next = False
            continue
        if argument == "--":
            break
        if argument.startswith("--"):
            if argument == "--expression":
                has_expression = expression_next = True
            elif argument.startswith("--expression="):
                has_expression = True
                scripts.append(argument.split("=", 1)[1])
            elif argument not in _SED_SAFE_LONG:
                return False
            continue
        if argument.startswith("-") and len(argument) > 1:
            safe, expression = _sed_short_flags(argument[1:])
            if not safe:
                return False
            if expression is not None:
                has_expression = True
                if expression:
                    scripts.append(expression)
                else:
                    expression_next = True
            continue
        if not has_expression and not scripts:
            scripts.append(argument)
        # Betikten sonraki konumsal argümanlar okunacak dosyalardır.
    if expression_next or not scripts:
        return False
    return all(_sed_script_reads_only(script) for script in scripts)


def _sed_short_flags(body: str) -> tuple[bool, str | None]:
    """Kısa bayrak kümesi güvenli mi, ve `-e` betiği var mı?

    `-n` → (True, None); `-ne 'p'` → (True, "") — betik sonraki argüman;
    `-e'p'` → (True, "p"); `-ni` → (False, None).
    """
    for index, char in enumerate(body):
        if char == "e":
            return True, body[index + 1 :]
        if char not in _SED_SAFE_SHORT:
            return False, None
    return True, None


def _sed_script_reads_only(script: str) -> bool:
    for match in _SED_SUBSTITUTE.finditer(script):
        if not set(match.group(2)) <= _SED_SAFE_SUBSTITUTE_FLAGS:
            return False
    rest = _SED_SUBSTITUTE.sub(" ", script)
    rest = _SED_TRANSLITERATE.sub(" ", rest)
    rest = _SED_ADDRESS.sub(" ", rest)
    return _SED_READ_ONLY_REST.match(rest) is not None


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
_REMOTE_READS = frozenset({"show", "get-url"})
#: Küme hâlinde yazılan kısa bayraklarda (`-vD`) aranan değiştirici harfler.
_BRANCH_MUTATING_SHORT = frozenset("dDmMcCfut")
_TAG_MUTATING_SHORT = frozenset("dasfmFue")


def git_reads_only(arguments: list[str]) -> bool:
    """git çağrısı depoda/dosyada hiçbir şey değiştirmiyor mu?"""
    if not arguments or arguments[0] not in READONLY_GIT_SUBCOMMANDS:
        return False
    sub, rest = arguments[0], arguments[1:]
    if any(argument.startswith("--output") for argument in rest):
        return False
    if sub == "branch":
        return _ref_listing_only(
            rest, _BRANCH_MUTATING, ("--set-upstream-to", "--track="), _BRANCH_MUTATING_SHORT
        )
    if sub == "tag":
        return _ref_listing_only(
            rest, _TAG_MUTATING, ("--message=", "--file="), _TAG_MUTATING_SHORT
        )
    if sub == "remote":
        # `git remote -v remove origin`: git `-v`'den sonra alt komutu da okur.
        return not rest or rest in (["-v"], ["--verbose"]) or rest[0] in _REMOTE_READS
    if sub == "symbolic-ref":
        positional = [argument for argument in rest if not argument.startswith("-")]
        return len(positional) <= 1 and not {"-d", "--delete"} & set(rest)
    return True


def _ref_listing_only(
    rest: list[str],
    mutating: frozenset[str],
    mutating_prefixes: tuple[str, ...],
    mutating_short: frozenset[str],
) -> bool:
    """`branch`/`tag` yalnız listeliyor mu? Konumsal ad, listeleme bayrağı olmadan oluşturur."""
    if any(argument in mutating or argument.startswith(mutating_prefixes) for argument in rest):
        return False
    bundles = (a[1:] for a in rest if a.startswith("-") and not a.startswith("--") and len(a) > 2)
    if any(set(bundle) & mutating_short for bundle in bundles):
        return False
    positional = [argument for argument in rest if not argument.startswith("-")]
    return not positional or bool(_LISTING_FLAGS & set(rest))
