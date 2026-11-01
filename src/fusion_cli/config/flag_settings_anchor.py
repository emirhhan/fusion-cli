"""`--settings` dosyasının dizini: o dosyadaki `/x` kalıbının dayanak noktası (#45).

Claude Code (code.claude.com/docs/en/permissions#where-a-pattern-anchors): `/path` ayar
kaynağına göre çözülür; `--settings <dosya>` ile gelen kuralda o dosyanın dizini. Satır içi
JSON ile verilen `--settings` için dosya yoktur, kalıp öteki kaynaklar gibi proje köküne
bağlanır.

`--settings` kuralları süreç ortamında taşınır (`config.flag_settings`, katman adı
`bayrak`); dosyanın dizini de aynı yolla taşınır ki aynı süreçteki alt ajanlar ve oturumdan
başlatılan alt süreçler aynı dayanak noktasını görsün. `--settings` dosyasını okuyan taraf
`record_settings_flag(ham_deger)` (ya da `set_flag_settings_dir(dosya)`) çağırır; satır içi
JSON'da kayıt silinir.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Süreç ortamında `--settings` dosyasının mutlak dizini.
FLAG_SETTINGS_DIR_ENV = "FUSION_FLAG_SETTINGS_DIR"
#: `--settings` izin katmanının kaynak adı (`config.flag_settings.LAYER_FLAG` ile aynı).
FLAG_LAYER_NAME = "bayrak"
#: `--settings` kurallarının taşıyabileceği kaynak adları: kök komut katmanı (`bayrak`) ve
#: `fusion -p` yolunun oturumluk kuralları (`cli/print_options.settings_rules`, `--settings`).
FLAG_LAYER_SOURCES = (FLAG_LAYER_NAME, "--settings")


def set_flag_settings_dir(settings_file: Path | None) -> None:
    """`--settings` dosyasını bu süreç için kaydet; `None` (satır içi JSON) kaydı siler."""
    if settings_file is None:
        os.environ.pop(FLAG_SETTINGS_DIR_ENV, None)
        return
    os.environ[FLAG_SETTINGS_DIR_ENV] = str(Path(settings_file).expanduser().resolve().parent)


def record_settings_flag(raw: str | None) -> None:
    """`--settings` bayrağının ham değerini kaydet: dosya yolu → dizini, satır içi JSON → yok.

    `load_settings` ile aynı ayrım: `{` ile başlayan değer JSON'dur. Bayrağı okuyan taraf
    (kök komut ve `-p`) bu tek çağrıyı yapar.
    """
    text = (raw or "").strip()
    set_flag_settings_dir(None if not text or text.startswith("{") else Path(text))


def flag_settings_dir() -> Path | None:
    """Kayıtlı `--settings` dizini; yoksa ya da göreli/bozuksa `None`."""
    raw = os.environ.get(FLAG_SETTINGS_DIR_ENV, "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_absolute() else None
