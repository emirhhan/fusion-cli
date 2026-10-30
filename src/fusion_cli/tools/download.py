"""Kamuya açık ikili kaynakları proje içine, baytları değiştirmeden indirir."""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
from pathlib import Path
from urllib.parse import urljoin

import httpx

from ..core.constants import MAX_DOWNLOAD_BYTES, MAX_WEB_REDIRECTS, WEB_TIMEOUT_S
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import require_str
from .files import display_path, writable_path
from .pinned_http import AsyncPinnedTransport
from .web import url_block_reason

#: Tüm indirmenin (yönlendirmeler dahil) toplam süre sınırı. `httpx` zaman aşımı OKUMA
#: başınadır; damla damla veren bir sunucu sonsuza dek açık tutabilirdi (ölçüldü, 30 Ekim).
DOWNLOAD_TOTAL_TIMEOUT_S = 300.0

#: Adı bu uzantılardan biri olan dosya HTML OLAMAZ: sunucu 200 ile hata sayfası verirse
#: `.png`/`.zip` adıyla diske girip sonradan "ZIP değil" diye patlıyordu.
_IKILI_UZANTILAR = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".zip", ".gz", ".tar", ".tgz"}
    | {".woff", ".woff2", ".ttf", ".otf", ".mp3", ".wav", ".ogg", ".mp4", ".webm", ".pdf"}
)
_HTML_BASLANGICLARI = (b"<!doctype html", b"<html", b"<head", b"<body")


def _html_hata_sayfasi_mi(path: Path, content: bytes | bytearray) -> bool:
    if path.suffix.lower() not in _IKILI_UZANTILAR:
        return False
    return bytes(content[:512]).lstrip().lower().startswith(_HTML_BASLANGICLARI)


async def _download_bytes(url: str, context: ToolContext) -> bytearray:
    """Her hedefi denetle; sıkıştırılmış yanıtın açılan baytlarını da sınırla."""
    current = url
    # Taşıma denetlenen IP'ye bağlanır (DNS rebinding; bkz. `pinned_http`).
    async with httpx.AsyncClient(
        follow_redirects=False, timeout=WEB_TIMEOUT_S, transport=AsyncPinnedTransport()
    ) as client:
        for _ in range(MAX_WEB_REDIRECTS + 1):
            reason = await asyncio.to_thread(url_block_reason, current)
            if reason:
                raise ValueError(reason)
            if context.cancelled.is_set():
                raise InterruptedError("İndirme iptal edildi.")
            async with client.stream("GET", current) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("Yönlendirme hedefi boş.")
                    current = urljoin(current, location)
                    continue
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                    if context.cancelled.is_set():
                        raise InterruptedError("İndirme iptal edildi.")
                    if len(body) + len(chunk) > MAX_DOWNLOAD_BYTES:
                        raise ValueError(f"İndirme {MAX_DOWNLOAD_BYTES} bayt sınırını aşıyor.")
                    body.extend(chunk)
                if not body:
                    raise ValueError("Kaynak boş dosya döndürdü.")
                return body
    raise ValueError(f"En fazla {MAX_WEB_REDIRECTS} yönlendirme aşıldı.")


def _save_new(path: Path, content: bytes, context: ToolContext) -> None:
    """Tamamlanan dosyayı atomik yayınla; mevcut dosyanın üzerine yazma."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        # NamedTemporaryFile dosyayı 0600 açar ve `os.link` bu izni hedefe taşır:
        # indirilen görsel/font web sunucusu ya da başka kullanıcı tarafından okunamıyordu
        # (`files.atomic_write` aynı sorunu zaten giderir). Normal dosya izni: 0666 & ~umask.
        umask = os.umask(0)
        os.umask(umask)
        temporary.chmod(0o666 & ~umask)
        if context.cancelled.is_set():
            raise InterruptedError("İndirme iptal edildi.")
        os.link(temporary, path)
        # EDİNİM: dosya indirildi, agent yazmadı. Adım düşse bile silinmez;
        # yeniden indirmek ağ, süre ve sağlayıcı kotası harcar.
        context.changes.record_acquired(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _hata_metni(error: Exception) -> str:
    """Hatayı OKUNUR bir cümleye çevir; boş mesajı türle doldur.

    Ölçüldü (13 Eylül, koşu 29): indirme `Dosya indirilemedi: ` mesajıyla düştü —
    iki nokta üst üsteden sonra hiçbir şey yoktu. httpx bağlantı/zaman aşımı
    hatalarının `str()` değeri boş olabiliyor; model neyin olduğunu göremediği için
    aynı adresi tekrar denedi ve adım kurtarma hakkını tüketti.
    """
    metin = str(error).strip()
    if metin:
        return metin
    ad = type(error).__name__
    if isinstance(error, TimeoutError | httpx.TimeoutException):
        return f"{ad}: sunucu zamanında cevap vermedi"
    if isinstance(error, httpx.ConnectError):
        return f"{ad}: sunucuya bağlanılamadı (adres ya da ağ)"
    return f"{ad}: sağlayıcı ayrıntı vermedi"


#: Adresin var olmadığını söyleyen HTTP durumları.
_YOK_DURUMLARI = frozenset({404, 410})


def _tahmin_uyarisi(error: Exception) -> str:
    """Adres yoksa ASIL hatayı söyle: URL ezberden uydurulmuş.

    Ölçüldü (13 Eylül, Godot koşusu): model `raw.githubusercontent.com` altında
    üç ayrı yol denedi, üçü de 404 döndü ve hiç `web_search` çağırmadı; sonra
    assetleri betikle ÜRETMEYE geçti. "İndirilemedi" demek bu döngüyü kırmıyor;
    yapılacak şeyin söylenmesi gerekiyor.

    Durum kodu YAPISAL okunur (30 Ekim): eskiden `"403" in str(error)` URL'deki
    `img_4031.png` gibi rakamlarda da tetikleniyor, 403'ü (bot/UA engeli) "adres yok"
    diye yorumlayıp modeli yanlış yönlendiriyordu.
    """
    if not isinstance(error, httpx.HTTPStatusError):
        return ""
    durum = error.response.status_code
    if durum in _YOK_DURUMLARI:
        return (
            "\nBu adres YOK. Aynı alan adı altında başka yol DENEME: adresi ezberden "
            "üretmek çalışmıyor. `web_search` ile indirme sayfasını bul, gerçek dosya "
            "bağlantısını oradan al (arşiv olabilir) ve onu indir."
        )
    if durum in (401, 403):
        return (
            "\nSunucu erişimi reddetti (bot/kimlik doğrulama engeli olabilir); adres var "
            "olabilir. Aynı adresi tekrar deneme: tarayıcıyla (browser_open) sayfadan "
            "indirme bağlantısını bul ya da başka bir kaynak seç."
        )
    return ""


async def download_file(args: ToolArgs, context: ToolContext) -> ToolResult:
    """İndirilen dosyanın gerçek boyutunu ve SHA-256 özetini kanıt olarak döndür."""
    path = writable_path(context, require_str(args, "path"))
    if path.exists():
        return ToolResult.failure("Hedef dosya zaten var; üzerine yazılmadı. Yeni bir yol seç.")
    url = require_str(args, "url")
    try:
        content = await asyncio.wait_for(
            _download_bytes(url, context), timeout=DOWNLOAD_TOTAL_TIMEOUT_S
        )
        if _html_hata_sayfasi_mi(path, content):
            raise ValueError(
                f"Sunucu {path.suffix} yerine HTML sayfası döndürdü (hata/engel sayfası "
                "olabilir); dosya kaydedilmedi."
            )
        _save_new(path, content, context)
    except TimeoutError:
        return ToolResult.failure(
            f"Dosya indirilemedi ({url}): toplam süre sınırı ({DOWNLOAD_TOTAL_TIMEOUT_S:g} sn) "
            "aşıldı; sunucu çok yavaş."
        )
    except (httpx.HTTPError, OSError, ValueError) as error:
        return ToolResult.failure(
            f"Dosya indirilemedi ({url}): {_hata_metni(error)}{_tahmin_uyarisi(error)}"
        )
    context.touched.add(path)
    digest = hashlib.sha256(content).hexdigest()
    return ToolResult(
        f"İndirildi: {display_path(context, path)}\n"
        f"Boyut: {len(content)} bayt\nSHA-256: {digest}\n"
        "Kaynağın lisansını ayrıca doğrula ve ASSETS.json içine kaydet. "
        "Dosya indirilmiş olması lisans veya dosya biçimi doğrulaması değildir."
    )
