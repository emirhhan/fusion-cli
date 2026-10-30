"""Optimize edilebilen istemler — açık bir izin listesi.

Her hedef, `src/fusion_cli` içindeki bir istem dosyasını ve o dosyayı İÇE AKTARIM
ANINDA okuyan modül değişkenini adlandırır. İzin listesi bilinçlidir: araç tanımı, güvenlik
ya da onay metinleri gibi davranışı sınırlayan metinler otomatik önerinin konusu olamaz.

Aday istem eval'de denenirken dosya değil bu modül değişkeni geçici olarak değiştirilir
(`override`); dosya yalnız kullanıcı `uygula` dediğinde yazılır.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import fusion_cli
from fusion_cli.core.atomic_file import atomic_replace_text
from fusion_cli.core.errors import EvalError

_PAKET = Path(fusion_cli.__file__).resolve().parent
_AJAN_ISTEMLERI = _PAKET / "engines" / "agent" / "prompts"
_AJAN_MODULU = "fusion_cli.engines.agent"


@dataclass(frozen=True, slots=True)
class PromptTarget:
    """Optimize edilebilir bir istem: adı, dosyası ve çalışma zamanındaki değişkeni."""

    name: str
    file: Path
    module: str
    attribute: str

    def read(self) -> str:
        return self.file.read_text(encoding="utf-8")

    def write(self, text: str) -> None:
        atomic_replace_text(self.file, text)


TARGETS: dict[str, PromptTarget] = {
    target.name: target
    for target in (
        PromptTarget(
            "system", _AJAN_ISTEMLERI / "system.md", f"{_AJAN_MODULU}.loop", "SYSTEM_PROMPT"
        ),
        PromptTarget(
            "system_chat",
            _AJAN_ISTEMLERI / "system_chat.md",
            f"{_AJAN_MODULU}.loop",
            "CHAT_SYSTEM_PROMPT",
        ),
        PromptTarget("review", _AJAN_ISTEMLERI / "review.txt", f"{_AJAN_MODULU}.review", "_PROMPT"),
        PromptTarget(
            "compress", _AJAN_ISTEMLERI / "compress.txt", f"{_AJAN_MODULU}.compaction", "_PROMPT"
        ),
    )
}


def get_target(name: str) -> PromptTarget:
    """Adı hedefe çöz; izin listesinde olmayan ad anlaşılır hatayla reddedilir."""

    try:
        return TARGETS[name]
    except KeyError:
        raise EvalError(
            f"optimize edilemeyen istem: {name!r} (izinli: {', '.join(TARGETS)})"
        ) from None


@contextmanager
def override(target: PromptTarget, text: str) -> Iterator[None]:
    """İstemi çalışma zamanında geçici olarak `text` yap; çıkışta ESKİSİNİ geri koy.

    Sıralı değerlendirme için yazıldı: görevler tek tek koşar, eşzamanlı iki
    değerlendirme aynı değişkeni çekiştirmez.
    """

    modul = importlib.import_module(target.module)
    eski = getattr(modul, target.attribute)
    setattr(modul, target.attribute, text)
    try:
        yield
    finally:
        setattr(modul, target.attribute, eski)
