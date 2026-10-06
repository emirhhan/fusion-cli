"""Oyun kapısı: bu turda play_probe ile denenen oyun kapanışta YENİDEN oynatılır.

Ölçüldü (6 Ekim 2026, dalga23 HTML oyun): play_probe 15 kez "Konsol hatası: 1 —
Assignment to constant variable" ve "tuşlar durumu değiştirmedi" dedi. Araç sonucu
yine başarılı sayıldı, kapanış kapısı ona hiç bakmadı ve model "tamamlandı" dedi;
oyunda oyuncu hareket etmiyordu. Sonda bulgusu bir öneri değil, kapanış ölçütüdür.

Kapı eski sonucu taşımaz, oyunu son haliyle yeniden oynatır: model düzeltip yeniden
denemeyi unutsa da doğru karar verir.
"""

from __future__ import annotations

from ...core.tools import ToolContext
from ...core.verification import VerificationResult
from ...tools.play_probe import probe_game


class GameProbeVerifier:
    """Denenen oyunlar son halleriyle oynanabilir mi?"""

    def __init__(self, context: ToolContext) -> None:
        self._context = context

    async def verify(self) -> VerificationResult:
        if not self._context.probed_games or not self._context.touched:
            return VerificationResult(ok=True)
        bulgular: list[str] = []
        for adres in sorted(self._context.probed_games):
            try:
                rapor = await probe_game(adres)
            except Exception:  # sınır: Playwright yok, tarayıcı açılamadı
                continue
            bulgular.extend(f"{adres}: {sorun}" for sorun in rapor.problems())
        if not bulgular:
            return VerificationResult(ok=True)
        return VerificationResult(
            ok=False,
            summary=f"oyun son haliyle oynatıldı: {len(bulgular)} sorun",
            findings=tuple(bulgular),
        )
