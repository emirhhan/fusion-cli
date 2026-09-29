"""Web oturumu üzerinden görsel üretimi (Gemini web, ChatGPT web).

Kullanıcının zaten bağlı olduğu web oturumu (çerezli, izole Chrome profili)
görseli üretir; Fusion üretilen görseli sayfadan alıp yerel dosyaya yazar.

Ölçüldü (26 Eylül, gemini_web, TR arayüz): görsel ~15 sn'de
`generated-image single-image img` öğesinde `blob:` adresiyle çizilir; blob
adresi `fetch` ile okunamıyor ("Failed to fetch"), ama görsel yüklü olduğu için
tuvale çizilip PNG olarak alınabiliyor (1024×559, 448 KB, geçerli PNG).
ChatGPT web seçicileri aynı sözleşmeyle yazıldı ama o gün oturum Cloudflare
doğrulamasındaydı; canlı ÖLÇÜLMEDİ.
"""

from __future__ import annotations

import asyncio
import base64
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config.models import WebSessionConfig
from .web_browser import (
    _POOL,
    BrowserProviderDefinition,
    BrowserSessionPool,
    WebBrowserError,
    _fill_editor,
    _first_visible,
    _open_ready_conversation,
    _raise_if_blocked_early,
    gemini_attach_file,
    provider_definition,
)
from .web_session import WebSessionCredential

#: Sağlayıcı başına üretilen görselin seçicileri (dardan genişe).
IMAGE_SELECTORS: dict[str, tuple[str, ...]] = {
    "gemini_web": ("generated-image img", "single-image img"),
    "chatgpt_web": (
        '[data-message-author-role="assistant"] img[alt]',
        'img[alt*="Generated" i]',
        'img[alt*="oluşturul" i]',
    ),
}
#: Referans görsel yükleyebilen sağlayıcılar. Gemini web'de canlı ölçüldü (29 Eylül):
#: FLUX ile üretilen kırmızı kask yüklendi, "kaskı mat siyah yap" istemiyle 34 sn'de
#: aynı kompozisyonda mat siyah kask döndü. ChatGPT web oturumu otomasyonda Cloudflare
#: doğrulamasına düştüğü için orada yükleme denenmez.
REFERENCE_PROVIDERS = frozenset({"gemini_web"})
#: Arayüz simgeleri ve avatarlar görsel sayılmaz; üretilen görseller ≥ 512 px
#: (ölçülen en küçük kenar 559).
MIN_IMAGE_EDGE = 256
#: Görselin çıkması için beklenen en uzun süre. Ölçülen 15 sn; yoğun saatte ve
#: ChatGPT'de dakikalar sürebildiği için geniş tutulur.
IMAGE_WAIT_S = 180.0
#: Görsel belirdikten sonra kararlı sayılmadan önce beklenen süre (animasyon).
IMAGE_SETTLE_S = 4.0
_POLL_S = 2.0
_BLOCK_CHECK_EVERY = 8

_PROMPT_PREFIX = "Bir görsel oluştur: "


@dataclass(frozen=True, slots=True)
class GeneratedImage:
    path: Path
    width: int
    height: int


def image_prompt(prompt: str) -> str:
    """Sağlayıcının görsel üretim niyetini tanıması için istemi hazırla."""
    metin = prompt.strip()
    kucuk = metin.lower()
    if kucuk.startswith(("bir görsel", "görsel oluştur", "resim", "generate", "create an image")):
        return metin
    return _PROMPT_PREFIX + metin


def save_images(
    payloads: Sequence[dict[str, Any]], out_dir: Path, *, now: datetime | None = None
) -> list[GeneratedImage]:
    """Sayfadan alınan `{b64, w, h}` kayıtlarını PNG dosyası olarak yaz."""
    out_dir.mkdir(parents=True, exist_ok=True)
    zaman = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    kayitlar: list[GeneratedImage] = []
    for sira, payload in enumerate(payloads, start=1):
        veri = base64.b64decode(str(payload.get("b64", "")))
        if not veri.startswith(b"\x89PNG"):
            continue
        yol = out_dir / f"fusion-{zaman}-{sira}.png"
        yol.write_bytes(veri)
        kayitlar.append(GeneratedImage(yol, int(payload.get("w", 0)), int(payload.get("h", 0))))
    return kayitlar


_FIND_IMAGES_JS = """(args) => {
  const [selectors, minEdge] = args;
  const seen = new Set();
  const out = [];
  for (const sel of selectors) {
    for (const img of document.querySelectorAll(sel)) {
      if (seen.has(img) || !img.complete) continue;
      seen.add(img);
      if (img.naturalWidth >= minEdge && img.naturalHeight >= minEdge) {
        out.push({ src: img.currentSrc, w: img.naturalWidth, h: img.naturalHeight });
      }
    }
  }
  return out;
}"""

_EXTRACT_JS = """(args) => {
  const [selectors, minEdge] = args;
  const out = [];
  const seen = new Set();
  for (const sel of selectors) {
    for (const img of document.querySelectorAll(sel)) {
      if (seen.has(img) || img.naturalWidth < minEdge || img.naturalHeight < minEdge) continue;
      seen.add(img);
      const c = document.createElement('canvas');
      c.width = img.naturalWidth; c.height = img.naturalHeight;
      c.getContext('2d').drawImage(img, 0, 0);
      out.push({ w: img.naturalWidth, h: img.naturalHeight,
                 b64: c.toDataURL('image/png').split(',')[1] });
    }
  }
  return out;
}"""


async def generate_images(
    session: WebSessionConfig,
    credential: WebSessionCredential,
    prompt: str,
    out_dir: Path,
    *,
    pool: BrowserSessionPool | None = None,
    wait_s: float = IMAGE_WAIT_S,
    reference: Path | None = None,
) -> list[GeneratedImage]:
    """Yeni bir sohbette görsel üret ve dosyaya yaz; üretilmezse `WebBrowserError`.

    `reference` verilirse görsel önce sohbete yüklenir. Yükleme olmazsa istem
    GÖNDERİLMEZ: referanssız üretilen görsel "düzenlendi/varyasyon" diye sunulursa
    yapılmamış iş yapılmış gibi görünürdü.
    """
    selectors = IMAGE_SELECTORS.get(session.provider)
    if not selectors:
        raise WebBrowserError(f"{session.provider} için görsel üretimi desteklenmiyor.")
    if reference is not None and session.provider not in REFERENCE_PROVIDERS:
        raise WebBrowserError(f"{session.provider} referans görsel yükleyemiyor.")
    definition = provider_definition(session.provider)
    manager = pool or _POOL
    async with manager.lock_for(session.provider, session.account):
        context = await manager.context_for(session, credential)
        page = await context.new_page()
        try:
            await _open_ready_conversation(page, definition)
            if reference is not None and not await gemini_attach_file(page, str(reference)):
                raise WebBrowserError(
                    f"Referans görsel {definition.name} sohbetine yüklenemedi; üretim yapılmadı."
                )
            girdi = await _first_visible(page, definition.input_selectors, timeout_ms=15_000)
            if girdi is None:
                raise WebBrowserError(f"{definition.name} mesaj alanı bulunamadı.")
            await _fill_editor(girdi, image_prompt(prompt))
            gonder = await _first_visible(page, definition.send_selectors, timeout_ms=2_000)
            await (gonder.click() if gonder is not None else girdi.press("Enter"))
            return await _wait_and_extract(page, definition, selectors, out_dir, wait_s)
        finally:
            await page.close()
            manager.schedule_idle_release(session.provider, session.account)


async def _wait_and_extract(
    page: Any,
    definition: BrowserProviderDefinition,
    selectors: tuple[str, ...],
    out_dir: Path,
    wait_s: float,
) -> list[GeneratedImage]:
    basla = time.monotonic()
    ilk_gorulen: float | None = None
    onceki: list[str] = []
    kontrol = 0
    while time.monotonic() - basla < wait_s:
        await asyncio.sleep(_POLL_S)
        kontrol += 1
        if kontrol % _BLOCK_CHECK_EVERY == 0:
            await _raise_if_blocked_early(page, definition)
        bulunan = await page.evaluate(_FIND_IMAGES_JS, [list(selectors), MIN_IMAGE_EDGE])
        kaynaklar = sorted(str(item.get("src", "")) for item in bulunan)
        if not kaynaklar:
            continue
        if kaynaklar != onceki:
            onceki, ilk_gorulen = kaynaklar, time.monotonic()
            continue
        if ilk_gorulen is not None and time.monotonic() - ilk_gorulen >= IMAGE_SETTLE_S:
            kayitlar = save_images(
                await page.evaluate(_EXTRACT_JS, [list(selectors), MIN_IMAGE_EDGE]), out_dir
            )
            if kayitlar:
                return kayitlar
    await _raise_if_blocked_early(page, definition)
    try:
        cevap = (await page.inner_text("body"))[-400:].strip()
    except Exception:
        cevap = ""
    raise WebBrowserError(
        f"{definition.name} {wait_s:.0f} sn içinde görsel üretmedi."
        + (f" Sayfadaki son metin: {cevap}" if cevap else "")
    )
