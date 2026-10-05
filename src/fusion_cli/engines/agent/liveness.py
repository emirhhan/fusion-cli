"""Sessiz model çağrısında sunucu canlılık yoklaması.

Ölçüldü (5 Ekim 2026): 90 dakikalık bir kabul koşusunun ~50 dakikası, NIM'in hiç parça
göndermediği beş bekleyişte (her biri 600 sn) geçti. Aynı anda yapılan sondada sunucu
yeni isteklere "Service temporarily overloaded" diyordu; asılı çağrı 613 sn boyunca tek
parça göndermeden bağlantı hatasıyla bitti. 600 sn sınırı bilerek seçilmişti: NIM büyük
bir dosyayı araç argümanı olarak yazarken de akışta parça göndermeyebiliyor, yani
"sessiz çalışan" ile "ölü" çağrı yalnız süreye bakarak ayırt edilemiyor.

Ayırt eden şey sunucunun kendisi: sessizlik uzayınca aynı modele (yedeksiz) çok küçük
bir istek gönderilir. Hata verirse ya da süresinde cevap gelmezse sunucu sağlıksızdır ve
beklemenin anlamı yoktur; hızlı cevap verirse model gerçekten çalışıyordur, beklenir.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace

from ...core.types import CompletionRequest, Message, ModelSpec, StreamDone
from ...providers.factory import build_provider

#: Hiç parça gelmeden bu kadar beklenince sunucu yoklanır. Yoklama çağrıyı KESMEZ,
#: yalnız sunucunun sağlığını sorar; bu yüzden en uzun başarılı çağrının (aynı gün
#: 163 sn) altında olabilir.
CHECK_AFTER_S = 90.0
#: Yoklamanın cevap sınırı. Sağlıklı sunucu küçük isteğe ölçülen ~1,6 sn'de cevap verdi.
PING_TIMEOUT_S = 30.0
#: Sağlıklı bulunan sunucunun yeniden yoklanmasından önceki süre.
RECHECK_S = 120.0
_PING_TEXT = "Yalnızca 'tamam' yaz."

#: Yoklama: sağlıklıysa None, değilse kısa neden.
Ping = Callable[[], Awaitable[str | None]]
#: Akıştan gelen parça sayısını okuyan fonksiyon (0 → hiç veri gelmedi).
ChunkCount = Callable[[], int]


def is_api_model(spec: ModelSpec) -> bool:
    """Web oturumu modelleri (ör. gemini_web/…) yoklanmaz: her yoklama bir sohbet açar."""
    return not spec.model.split("/", 1)[0].endswith("_web")


def ping_for(spec: ModelSpec) -> Ping:
    """Aynı modele, yedek zinciri OLMADAN küçük bir istek gönderen yoklama."""
    yalniz = replace(spec, fallback=())

    async def _ping() -> str | None:
        provider = build_provider(yalniz, publisher=None, retry_delays_s=())
        istek = CompletionRequest(
            messages=(Message("user", _PING_TEXT),),
            temperature=0.0,
            max_tokens=16,
            timeout_s=PING_TIMEOUT_S,
        )
        try:
            async with asyncio.timeout(PING_TIMEOUT_S):
                async for item in provider.stream(istek):
                    if isinstance(item, StreamDone):
                        sonuc = item.result
                        return None if sonuc.ok else (sonuc.error or "yoklama başarısız")[:160]
        except TimeoutError:
            return f"yoklamaya {PING_TIMEOUT_S:.0f} sn içinde cevap yok"
        except Exception as exc:  # sınır: sağlayıcı istisnası sağlıksızlık sayılır
            return f"yoklama hatası: {type(exc).__name__}"
        return "yoklama sonuç üretmeden bitti"

    return _ping


async def watch(chunks: ChunkCount, ping: Ping) -> str:
    """Sessizlik sürdükçe sunucuyu yokla; sağlıksızsa nedenini döndür.

    Akıştan herhangi bir parça (düşünme ya da araç argümanı dahil) gelirse sunucu
    canlıdır ve izleme kendiliğinden biter: sonraki boşlukları parça başı sınır keser.
    Sağlıklı sunucuda bu korutin hiç dönmez; çağıran tarafından iptal edilir.
    """
    await asyncio.sleep(CHECK_AFTER_S)
    while chunks() == 0:
        neden = await ping()
        if neden is not None:
            return neden
        await asyncio.sleep(RECHECK_S)
    await asyncio.Event().wait()  # canlı akış: kapanana kadar bekle (iptal edilir)
    return ""  # pragma: no cover - ulaşılmaz
