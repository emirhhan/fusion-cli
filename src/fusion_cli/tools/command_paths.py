"""Kabuk komutu argümanlarında proje kökünün DIŞINA çıkan yol tespiti.

`read_file` proje dışını `resolve_path` ile engelliyor; ama aynı dosya kabuktan
`cat ~/.ssh/id_rsa` ile okunabiliyordu ve `cat` salt-okur bir komut olduğu için
auto kipte sorulmadan çalışıyordu (17 Eylül denetimi, F1). Salt-okur olmak yeterli
değil: NEYİ okuduğu da önemli.

Tam kabuk ayrıştırması imkânsızdır (değişken, glob, takma ad, alt kabuk). Bu yüzden
denetim bilinçli olarak YANLIŞ POZİTİFE meyillidir: projeden çıkıp çıkmadığını
kanıtlayamadığımız her yol "proje dışı" sayılır ve komut onaya düşer. Bedel
asimetriktir — gereksiz bir soru kullanıcıyı yorar, atlanan bir soru sırrı sızdırır.

Proje kökü burada bilinmez (`command_policy` köksüz çağrılır); bu yüzden her mutlak
yol proje dışı sayılır. Proje içindeki bir dosyaya mutlak yolla erişen komut da
sorulur — göreli yol kullanan komut sorulmaz.
"""

from __future__ import annotations

import posixpath
import re

#: İlk konumsal argümanı YOL değil DESEN/PROGRAM olan araçlar.
#:
#: `grep "^/api" src` ya da `awk '/x/ {print $1}' a.txt` içindeki ilk argüman bir
#: dosya yolu değildir; yol gibi denetlenirse zararsız aramalar onaya düşerdi.
_PATTERN_TOOLS = frozenset({"grep", "egrep", "fgrep", "rg", "ag", "sed", "awk", "jq"})

#: Deseni/programı AYRI bir bayrakla alan seçenekler. Bunlardan biri varsa ilk
#: konumsal argüman artık desen değil dosyadır (`grep -e x /etc/passwd`,
#: `awk -f /yol/prog.awk`) ve atlanmaz.
_PATTERN_SOURCE_FLAGS = frozenset({"-e", "-f", "--file", "--regexp", "--expression", "--from-file"})

#: Kök dışında olduğu hâlde okunması/yazılması hiçbir şey sızdırmayan yollar.
_HARMLESS_ABSOLUTE_PATHS = frozenset({"/dev/null"})

#: Kısa seçeneğe yapışık değer: `-o/tmp/x`, `-I~/inc`, `-f../prog`.
_ATTACHED_VALUE = re.compile(r"^-[A-Za-z]+([/~$].*|\.\.(?:/.*)?)$")


def escapes_project(name: str, arguments: list[str]) -> bool:
    """Komutun argümanlarından biri proje kökünün dışını gösteriyor olabilir mi?

    Mutlak yol, `~` ile başlayan yol, `$` ile değişken (`$HOME`, `$X/..`) ve `..`
    ile kökün üstüne çıkan göreli yol "proje dışı" sayılır.
    """
    return any(_escapes(candidate) for candidate in _path_candidates(name, arguments))


def _path_candidates(name: str, arguments: list[str]) -> list[str]:
    """Yol olabilecek bütün parçalar: argümanın kendisi ve `=`/yapışık değeri."""
    should_skip_pattern = name in _PATTERN_TOOLS and not any(
        argument.split("=", 1)[0] in _PATTERN_SOURCE_FLAGS for argument in arguments
    )
    candidates: list[str] = []
    for argument in arguments:
        if should_skip_pattern and not argument.startswith("-"):
            should_skip_pattern = False
            continue
        candidates.extend(_argument_values(argument))
    return candidates


def _argument_values(argument: str) -> list[str]:
    values = [argument]
    if "=" in argument:
        # `--config=/etc/x`, `PREFIX=~/x`: atamanın sağ tarafı da bir yoldur.
        values.append(argument.split("=", 1)[1])
    attached = _ATTACHED_VALUE.match(argument)
    if attached is not None:
        values.append(attached.group(1))
    return values


def _escapes(candidate: str) -> bool:
    if "$" in candidate:
        # Değişkenin neye açılacağını bilemeyiz; `$HOME/.ssh` de olabilir.
        return True
    if candidate.startswith("~"):
        return True
    if candidate.startswith("/"):
        return candidate not in _HARMLESS_ABSOLUTE_PATHS
    normalized = posixpath.normpath(candidate)
    return normalized == ".." or normalized.startswith("../")
