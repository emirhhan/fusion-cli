"""`fusion -p --plugin-dir <yol>…` — oturumluk eklentiler (#301; eklenti alanı #401 ile ortak).

Claude: `--plugin-dir` eklentiyi kurmadan yalnız bu oturum için yükler; bayrak tekrarlanır.
Kök komutta eklenti alanı yolları `CLAUDE_CODE_PLUGIN_DIRS` ortam değişkenine (os.pathsep
ile ayrılmış, çözülmüş mutlak yollar) ekler ve katalog/eklenti listesi oradan okur.
`-p` yolu kök seçeneklerinden geçmediği (argv `print` alt komutuna çevrilir) için aynı
sözleşme burada uygulanır: koşu, alt ajanlar ve alt süreçler aynı listeyi görür.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

PLUGIN_DIRS_ENV = "CLAUDE_CODE_PLUGIN_DIRS"


def add_plugin_dirs(paths: Iterable[str | Path]) -> None:
    """Yolları ortam listesine ekle (var olanlar korunur, tekrar eklenmez)."""
    given = [str(Path(p).expanduser().resolve()) for p in paths if str(p).strip()]
    if not given:
        return
    current = [p for p in os.environ.get(PLUGIN_DIRS_ENV, "").split(os.pathsep) if p]
    merged = list(dict.fromkeys([*current, *given]))
    os.environ[PLUGIN_DIRS_ENV] = os.pathsep.join(merged)
