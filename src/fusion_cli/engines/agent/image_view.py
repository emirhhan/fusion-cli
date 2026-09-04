"""Yerel bir görsele BAK: dosya adı içeriği anlatmaz.

Ölçülen hata: kullanıcı `assets/sprites/player.png` verdi, agent onu oyuncu
karakteri sanıp sahneye koydu. Dosya aslında bir uygulama ikonuydu ve oyun
"karakter" yerine logoyla çıktı. Agent'ın 24 aracının hiçbiri diskteki bir
görseli açamıyordu; `read_file` "Metin dosyası değil" diyor. Yani hatayı fark
etmesi MÜMKÜN DEĞİLDİ.

Kusur alana özgü değil: asset kullanan her iş (oyun, web tasarımı, sunum)
görsel körlüğüyle yapılıyordu.

Görsel, agent modeline değil YAPILANDIRILMIŞ GÖRSEL MODELİNE (`config.vision`)
gönderilir ve metin açıklaması döner. Böylece araç, agent modeli çok kipli
olmasa da (ör. tarayıcıdan kazınan web modelleri) çalışır.
"""

from __future__ import annotations

import base64
from pathlib import Path

from ...config.models import Config
from ...core.types import CompletionRequest, Message
from ...providers.web_registry import web_registry_for

#: Tek bir görselin üst sınırı. Uygulamanın ek dosya sınırıyla aynı tutulur.
MAX_IMAGE_BYTES = 5 * 1024 * 1024

#: Görsel modeline gönderilebilen biçimler ve MIME karşılıkları.
IMAGE_MIME: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}

#: Soru verilmediğinde sorulan varsayılan soru.
#:
#: "Bu ne?" yetmiyor: agent'ın ihtiyacı olan şey, dosyanın İŞE UYGUN olup
#: olmadığına karar verebilmek. Bu yüzden tür, konu ve kullanım uygunluğu
#: birlikte istenir.
DEFAULT_QUESTION = (
    "Bu görselde tam olarak ne var? Şunları söyle: (1) türü — logo/ikon mu, "
    "karakter sprite'ı mı, doku/zemin mi, fotoğraf mı, ekran görüntüsü mü; "
    "(2) ana konusu ve baskın renkleri; (3) saydam arka planı var mı; "
    "(4) bir oyunda ya da arayüzde hangi amaçla kullanılabilir, hangi amaçla "
    "kullanılmamalı. Kısa ve somut yaz."
)

VISION_MAX_TOKENS = 400
VISION_TIMEOUT_S = 60.0


def load_image_data_uri(path: Path) -> tuple[str, str | None]:
    """Görseli `data:` URI'ye çevir. Sorun varsa (uri, None) yerine (\"\", sebep)."""
    mime = IMAGE_MIME.get(path.suffix.casefold())
    if mime is None:
        desteklenen = ", ".join(sorted(IMAGE_MIME))
        return "", (
            f"Bu bir görsel dosyası değil (desteklenen uzantılar: {desteklenen}). "
            "Metin dosyalarını read_file ile oku."
        )
    if not path.is_file():
        return "", "Dosya bulunamadı; yolu list_dir ya da glob ile doğrula."
    boyut = path.stat().st_size
    if boyut > MAX_IMAGE_BYTES:
        return "", (
            f"Görsel çok büyük ({boyut // 1024} KB); sınır "
            f"{MAX_IMAGE_BYTES // 1024} KB. Küçültülmüş bir kopyasına bak."
        )
    ham = path.read_bytes()
    return f"data:{mime};base64," + base64.b64encode(ham).decode(), None


async def describe_image(config: Config, path: Path, question: str) -> tuple[str, str | None]:
    """Görseli yapılandırılmış görsel modeline sor. (açıklama, hata) döndürür."""
    from ...providers.factory import build_provider

    spec = config.vision
    if spec is None:  # pragma: no cover - araç yalnızca spec varken kaydedilir
        return "", "Görsel modeli yapılandırılmamış."
    data_uri, sorun = load_image_data_uri(path)
    if sorun is not None:
        return "", sorun
    provider = build_provider(
        spec,
        publisher=None,
        retry_delays_s=config.runtime.retry_delays_s,
        background=True,
        web_sessions=web_registry_for(config),
    )
    result = await provider.complete(
        CompletionRequest(
            messages=(Message("user", question, images=(data_uri,)),),
            temperature=config.runtime.utility_temperature,
            max_tokens=VISION_MAX_TOKENS,
            timeout_s=VISION_TIMEOUT_S,
            max_retries=0,
        )
    )
    if not result.ok:
        # Asıl sebep YUTULMAZ. Ölçüldü: yapılandırılmış görsel modeli EOL olup
        # 410 Gone dönüyordu; "yanıt vermedi" demek hem modeli hem kullanıcıyı
        # boşuna yeniden denemeye iter — config değişmeden hiçbir deneme tutmaz.
        return "", f"Görsel modeli ({spec.model}) başarısız: {result.error or 'bilinmeyen hata'}"
    if not result.text.strip():
        return "", f"Görsel modeli ({spec.model}) boş yanıt döndürdü."
    return result.text.strip(), None
