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

import asyncio
import base64
import re
from pathlib import Path

from ...config.models import Config
from ...core.errors import ConfigError, ProviderError
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
    "Bu görselde ne var? Türünü söyle (logo/ikon, karakter sprite'ı, doku/zemin, "
    "fotoğraf ya da ekran görüntüsü) ve konusunu bir cümleyle anlat. "
    "En fazla iki cümle yaz, tekrar etme."
)

#: Görsel modeli yanıt sınırı. Kısa tutulur: ölçüldü, 11b model uzun bütçede
#: aynı cümleyi tekrarlayarak döngüye giriyor.
VISION_MAX_TOKENS = 200
#: Yalnız yapılandırılmış `truncated` sonucundan sonra bir kez genişletilir.
#: Reasoning token'ları da aynı bütçeyi tüketir; bu sınır yeterlilik garantisi değil,
#: kısa görsel açıklaması için sınırlı bir kurtarma bütçesidir.
VISION_RECOVERY_MAX_TOKENS = 4096
VISION_TIMEOUT_S = 60.0


_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def collapse_repeats(text: str) -> str:
    """Aynı cümlenin tekrarlarını ayıkla.

    Ölçüldü: 11b görsel modeli "Bir oyun logosu olarak kullanılabilir." cümlesini
    sekiz kez üretti. Küçük modeller döngüye girebiliyor; tekrar bilgi katmaz ama
    isteme giren metni şişirir. Sıra korunur, ilk görülen kalır.
    """
    gorulen: set[str] = set()
    tutulan: list[str] = []
    # Cümle sınırı yalnız noktalama + BOŞLUKTUR (`(?<=[.!?])\s+`). Eskiden metin her
    # "." karakterinde bölünüp ". " ile birleştiriliyordu: "player.png" -> "player. png",
    # "v1.2", "3.5", "example.com" bozuluyordu (A2-08, ölçüldü 29 Ekim). Bu çıktı
    # agent'ın "karakter mi ikon mu" kararının tek kanıtıdır.
    for parca in _SENTENCE_BOUNDARY.split(text.replace("\n", " ")):
        cumle = parca.strip()
        if not cumle:
            continue
        anahtar = cumle.rstrip(".!?").strip().casefold()
        if anahtar in gorulen:
            continue
        gorulen.add(anahtar)
        tutulan.append(cumle)
    return " ".join(tutulan)


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
    # Uzantıya değil İÇERİĞE bakılır (A2-39): uzantısı `.png` olan SVG/ikon/bozuk dosya
    # sağlayıcıda sert hata veriyordu; burada anlaşılır bir mesajla elenir.
    if not any(ham.startswith(imza) for imza in _MAGIC.get(mime, ())) and not _is_webp(ham, mime):
        return "", (
            f"Dosya uzantısı {path.suffix} ama içeriği bu biçimde bir görsel değil "
            "(SVG, bozuk ya da yanlış adlandırılmış olabilir)."
        )
    return f"data:{mime};base64," + base64.b64encode(ham).decode(), None


#: MIME -> dosya başı imzaları. WebP ayrıca `_is_webp` ile doğrulanır.
_MAGIC: dict[str, tuple[bytes, ...]] = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    "image/bmp": (b"BM",),
}


def _is_webp(ham: bytes, mime: str) -> bool:
    return mime == "image/webp" and ham[:4] == b"RIFF" and ham[8:12] == b"WEBP"


async def describe_image(config: Config, path: Path, question: str) -> tuple[str, str | None]:
    """Görseli yapılandırılmış görsel modeline sor. (açıklama, hata) döndürür."""
    from ...config.model_lookup import configured_model_specs
    from ...providers.factory import build_provider

    spec = config.vision
    if spec is None:  # pragma: no cover - araç yalnızca spec varken kaydedilir
        return "", "Görsel modeli yapılandırılmamış."
    # Dosya okuma olay döngüsünü bloklamasın (A2-39): 5 MB'a kadar senkron okuma.
    data_uri, sorun = await asyncio.to_thread(load_image_data_uri, path)
    if sorun is not None:
        return "", sorun
    try:
        provider = build_provider(
            spec,
            publisher=None,
            retry_delays_s=config.runtime.retry_delays_s,
            background=True,
            web_sessions=web_registry_for(config),
            model_specs=configured_model_specs(config),
        )
        # Kısa, başarılı çağrının eski bütçesi korunur. Bütçe düşünme sırasında
        # dolarsa AYNI 200 token isteği tekrarlanmaz; tek kurtarma da ilk çağrının
        # kalan süresini paylaşır. Kesilmiş metin görsel kanıt diye kullanılmaz.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + VISION_TIMEOUT_S
        async with asyncio.timeout_at(deadline):
            for max_tokens in (VISION_MAX_TOKENS, VISION_RECOVERY_MAX_TOKENS):
                result = await provider.complete(
                    CompletionRequest(
                        messages=(Message("user", question, images=(data_uri,)),),
                        temperature=config.runtime.utility_temperature,
                        max_tokens=max_tokens,
                        timeout_s=max(0.001, deadline - loop.time()),
                        max_retries=0,
                    )
                )
                if not result.truncated:
                    break
            else:
                return "", (
                    f"Görsel modeli ({spec.model}) {VISION_RECOVERY_MAX_TOKENS} tokenlık "
                    "görsel açıklama bütçesinde de tamamlanmadı. "
                    "Görseli veya soruyu daralt ya da başka bir görsel modeli seç."
                )
    except TimeoutError:
        return "", f"Görsel modeli ({spec.model}) için süre sınırı aşıldı."
    except (ConfigError, ProviderError) as error:
        # Kurulamayan görsel sağlayıcısı aracı düşürmez, açıklayıcı hata döner.
        return "", f"Görsel modeli ({spec.model}) kullanılamıyor: {error}"
    if not result.ok:
        # Asıl sebep YUTULMAZ. Ölçüldü: yapılandırılmış görsel modeli EOL olup
        # 410 Gone dönüyordu; "yanıt vermedi" demek hem modeli hem kullanıcıyı
        # boşuna yeniden denemeye iter — config değişmeden hiçbir deneme tutmaz.
        return "", f"Görsel modeli ({spec.model}) başarısız: {result.error or 'bilinmeyen hata'}"
    if not result.text.strip():
        return "", f"Görsel modeli ({spec.model}) boş yanıt döndürdü."
    return collapse_repeats(result.text.strip()), None
