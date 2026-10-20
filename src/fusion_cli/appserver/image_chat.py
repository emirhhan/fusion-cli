"""`/görsel`: ChatGPT'deki gibi sohbetin içinden görsel üret.

Komut modele gitmez: aynı çekirdek (`image_create.create_image`) görseli galeriye üretir ve
sohbet cevabı olarak görseli gösteren bir markdown döner. Böylece görsel sohbet geçmişine
girer, "Görsel oluştur" sayfasındaki galeride de durur.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..config.models import Config
from ..providers.nim_image import ASPECT_SIZES
from .image_create import create_image

#: `/görsel`, `/gorsel` ve çoğul/ek biçimleri.
_COMMAND = re.compile(r"^/g[öo]rsel(?:i|ler)?(?:\s+(?P<rest>.*))?$", re.IGNORECASE | re.DOTALL)
_ASPECT_OPTION = re.compile(r"(?:^|\s)--(?:oran|aspect)[ =](?P<value>\d+:\d+)(?=\s|$)")
DEFAULT_ASPECT = "1:1"
USAGE = (
    "Kullanım: `/görsel <ne çizileceği>` — örnek: `/görsel gün batımında bir dağ evi`. "
    "İstersen `--oran 16:9` ekle. Desteklenen oranlar: " + ", ".join(ASPECT_SIZES) + "."
)


@dataclass(frozen=True, slots=True)
class ImageCommand:
    """Ayrıştırılmış `/görsel` isteği."""

    prompt: str
    aspect: str = DEFAULT_ASPECT


def parse_image_command(task: str) -> ImageCommand | None:
    """Görev bir `/görsel` komutuysa ayrıştır; değilse `None`. Boş istem de komuttur."""
    match = _COMMAND.match(task.strip())
    if match is None:
        return None
    rest = (match.group("rest") or "").strip()
    aspect = DEFAULT_ASPECT
    option = _ASPECT_OPTION.search(rest)
    if option is not None:
        aspect = option.group("value")
        rest = (rest[: option.start()] + rest[option.end() :]).strip()
    return ImageCommand(prompt=rest, aspect=aspect)


def _escape_alt(prompt: str) -> str:
    flat = " ".join(prompt.split())[:120]
    return flat.replace("[", "(").replace("]", ")")


async def run_image_command(config: Config, command: ImageCommand) -> tuple[bool, str]:
    """(başarılı_mı, sohbet markdown'ı). Hata metni kullanıcıya gösterilebilir."""
    if not command.prompt:
        return False, USAGE
    result: dict[str, Any] = await create_image(
        config, {"istem": command.prompt, "oran": command.aspect}
    )
    if result.get("ok") is not True:
        return False, str(result.get("metin") or "Görsel üretilemedi.")
    files = result.get("dosyalar") or []
    if not files:
        return False, "Sağlayıcı görsel döndürmedi."
    # ChatGPT'deki gibi: yalnız görsel. Sağlayıcı/boyut/galeri notu sohbete yazılmaz.
    alt = _escape_alt(command.prompt)
    return True, "\n\n".join(f"![{alt}](<{item['yol']}>)" for item in files)
