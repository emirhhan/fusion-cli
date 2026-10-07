"""Oyun kapısı: bu turda play_probe ile denenen oyun kapanışta YENİDEN oynatılır.

Ölçüldü (6 Ekim 2026, dalga23 HTML oyun): play_probe 15 kez "Konsol hatası: 1 —
Assignment to constant variable" ve "tuşlar durumu değiştirmedi" dedi. Araç sonucu
yine başarılı sayıldı, kapanış kapısı ona hiç bakmadı ve model "tamamlandı" dedi;
oyunda oyuncu hareket etmiyordu. Sonda bulgusu bir öneri değil, kapanış ölçütüdür.

Kapı eski sonucu taşımaz, oyunu son haliyle yeniden oynatır: model düzeltip yeniden
denemeyi unutsa da doğru karar verir.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ...core.tools import ToolContext
from ...core.verification import VerificationResult
from ...tools.play_probe import probe_game

_LOG = logging.getLogger(__name__)

#: index.html dosyadan açıldığında çıkan bulguların öneki.
DOSYADAN = (
    "index.html dosyadan (çift tıklayarak, file://) açılınca — kullanıcı böyle açar; "
    '`type="module"`, fetch ve import file:// ile engellenir, gerekirse klasik <script> '
    "kullan ya da modülleri tek dosyada birleştir"
)


class GameProbeVerifier:
    """Denenen oyunlar son halleriyle oynanabilir mi?"""

    def __init__(self, context: ToolContext) -> None:
        self._context = context

    async def verify(self) -> VerificationResult:
        if not self._context.touched:
            return VerificationResult(ok=True)
        bulgular: list[str] = []
        adresler = set(self._context.probed_games)
        # Kullanıcı oyunu index.html'e çift tıklayarak açar. Ölçüldü (dalga24): type=module
        # oyun http'de çalıştı, file:// ile CORS yüzünden hiç yüklenmedi; Fusion yalnız
        # kendi önizleme sunucusunda denemişti.
        index = self._context.root / "index.html"
        dosya = index.as_uri() if index.is_file() else None
        # Oyun hiç denenmediyse de kapı çalışır — istek bir oyun isteğiyse ve canvas'lı
        # index.html bu turda yazıldıysa. Oyun olmayan canvas sayfası (grafik, demo) sayılmaz.
        if not adresler and (
            "oyun" not in self._context.task_kinds
            or dosya is None
            or not _is_canvas_page(index, self._context)
        ):
            return VerificationResult(ok=True)
        if dosya is not None:
            adresler.add(dosya)
        for adres in sorted(adresler):
            try:
                rapor = await probe_game(adres)
            except Exception as error:  # sınır: Playwright yok, tarayıcı açılamadı
                _LOG.warning("Oyun sondası çalıştırılamadı", exc_info=True)
                bulgular.append(
                    f"{adres}: oyun doğrulanamadı ({type(error).__name__}); "
                    "Playwright/tarayıcı kurulumunu kontrol edip oyunu yeniden dene"
                )
                continue
            onek = f"{adres}: " if adres != dosya else f"{DOSYADAN}: "
            bulgular.extend(onek + sorun for sorun in rapor.problems())
        if not bulgular:
            return VerificationResult(ok=True)
        return VerificationResult(
            ok=False,
            summary=f"oyun son haliyle oynatıldı: {len(bulgular)} sorun",
            findings=tuple(bulgular),
        )


def _is_canvas_page(index: Path, context: ToolContext) -> bool:
    """index.html bu turda yazılan bir canvas sayfası mı (oyun adayı)?"""
    if not any(p.suffix.lower() in {".html", ".js"} for p in context.touched):
        return False
    try:
        return "<canvas" in index.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return False
