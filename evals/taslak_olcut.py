"""Taslak için başarı ölçütü çıkarımı — yalnız KANITTAN, uydurma yok.

Bir konuşmadan "bu görev doğru bitti mi" ölçütünü güvenle çıkarmak çoğu zaman
imkânsızdır. Bu modül yalnız turun kendi kanıtının izin verdiği iki durumda bir
ölçüt önerir; kalan durumda `None` döner ve kabulde kullanıcıdan ölçüt istenir:

1. Turda bir DOĞRULAMA komutu (test, lint, tip denetimi) çalıştırıldıysa:
   `exit_code` = 0 ölçütü, aynı komutla.
2. Tur dosya değiştirdiyse: `file_changed` ölçütü, ilk değişen dosyayla.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Mapping, Sequence
from pathlib import Path

from evals.tasks import CriterionKind, SuccessCriterion
from evals.taslak_maske import maskele

#: Kabuk aracının adı ve komut argümanı (`tools.builtin` içindeki `run_shell`).
KABUK_ARACI = "run_shell"
#: Doğrulama komutu sayılan başlangıçlar. Dar tutulur: ölçüt olarak kümeye girecek
#: komut yeniden çalıştırılacaktır, yalnızca okuma/denetim niteliğinde olmalıdır.
_DOGRULAMA = re.compile(
    r"^(?:python3? -m pytest|pytest|python3? -m unittest|npm (?:run )?test|npx vitest|"
    r"npx jest|npx tsc|ruff (?:check|format --check)|mypy|cargo (?:test|check|clippy)|"
    r"go (?:test|vet)|make (?:check|test|lint))\b"
)
#: Kabuk birleştirme/yönlendirme/ikame karakteri taşıyan komut ölçüt OLAMAZ.
_TEHLIKELI = re.compile(r"[;&|`$<>\n\\]")


def dogrulama_komutu(komut: str) -> str | None:
    """Komut güvenli bir doğrulama komutuysa kırpılmış hâli, değilse `None`."""

    temiz = komut.strip()
    if not temiz or _TEHLIKELI.search(temiz) or not _DOGRULAMA.match(temiz):
        return None
    try:
        shlex.split(temiz)
    except ValueError:
        return None
    return temiz


def olcut_cikar(
    kayitlar: Sequence[Mapping[str, object]], *, kok: Path, ev: Path | None
) -> tuple[SuccessCriterion | None, str]:
    """Turun kayıtlarından ölçüt ve gerekçesini çıkar; kanıt yoksa `(None, neden)`."""

    komut = _son_dogrulama(kayitlar)
    if komut is not None:
        return (
            SuccessCriterion(
                kind=CriterionKind.EXIT_CODE,
                expected_exit_code=0,
                command=maskele(komut, kok=kok, ev=ev),
            ),
            "turda çalışan doğrulama komutundan türetildi",
        )
    yol = _ilk_degisen(kayitlar)
    if yol is not None:
        return (
            SuccessCriterion(
                kind=CriterionKind.FILE_CHANGED, expected_path=maskele(yol, kok=kok, ev=ev)
            ),
            "turda değişen ilk dosyadan türetildi (zayıf ölçüt: içeriği doğrulamaz)",
        )
    return None, "turda doğrulama komutu ya da dosya değişikliği yok; ölçütü kabulde sen ver"


def _son_dogrulama(kayitlar: Sequence[Mapping[str, object]]) -> str | None:
    bulunan: str | None = None
    for kayit in kayitlar:
        if kayit.get("event") != "ToolExecuted" or kayit.get("name") != KABUK_ARACI:
            continue
        args = kayit.get("args")
        if not isinstance(args, Mapping):
            continue
        komut = args.get("command")
        if isinstance(komut, str):
            dogrulama = dogrulama_komutu(komut)
            if dogrulama is not None:
                bulunan = dogrulama
    return bulunan


def _ilk_degisen(kayitlar: Sequence[Mapping[str, object]]) -> str | None:
    for kayit in kayitlar:
        if kayit.get("event") != "FilesChanged":
            continue
        yollar = kayit.get("paths")
        if isinstance(yollar, list) and yollar and isinstance(yollar[0], str):
            return yollar[0]
    return None
