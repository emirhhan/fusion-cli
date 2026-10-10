"""Üzerine yazmada kaybolan ama hâlâ kullanılan üst düzey tanımlar.

Ölçüldü (10 Ekim 2026, dalga46 oyun koşusu): model 747 satırlık game.js'i iki
`write_file` ile "devamı" diye yazdı; ikinci çağrı ilkini ezdi, `GameState` ve
`CONFIG` tanımları kayboldu, oyun "GameState is not defined" ile hiç açılmadı.
Model bunu ancak süre dolarken fark etti. Yazma başarılıdır ama sonuç bunu söyler.
"""

from __future__ import annotations

import re

#: Satır başındaki üst düzey tanımlar (JS/TS ve Python). Girintili (sınıf içi)
#: tanımlar bilerek dışarıda: yeniden yazılan dosyada yer değiştirmeleri olağan.
_DEFINITION = re.compile(
    r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?"
    r"(?:const|let|var|function\*?|class|def)\s+([A-Za-z_$][\w$]*)",
    re.MULTILINE,
)


def _defined(source: str) -> set[str]:
    return set(_DEFINITION.findall(source))


def lost_definitions(before: str, after: str) -> tuple[str, ...]:
    """Önceki içerikte tanımlı, yenide tanımı olmayan ama yenide kullanılan adlar."""
    kalan = _defined(after)
    kayip = _defined(before) - kalan
    return tuple(
        sorted(ad for ad in kayip if re.search(rf"(?<![\w$]){re.escape(ad)}(?![\w$])", after))
    )
