"""Sessiz model çağrısında sunucu canlılık yoklaması.

Ölçüldü (5 Ekim 2026): 90 dakikalık bir kabul koşusunun ~50 dakikası, NIM'in hiç parça
göndermediği beş bekleyişte (her biri 600 sn) geçti. Aynı anda yapılan sondada sunucu
yeni isteklere "Service temporarily overloaded" diyordu; asılı çağrı 613 sn boyunca tek
parça göndermeden bağlantı hatasıyla bitti. 600 sn sınırı bilerek seçilmişti: NIM büyük
bir dosyayı araç argümanı olarak yazarken de akışta parça göndermeyebiliyor, yani
"sessiz çalışan" ile "ölü" çağrı yalnız süreye bakarak ayırt edilemiyor.

Sessizlik uzayınca aynı modele (yedeksiz) küçük bir istek gönderilir. Ancak bu
bağımsız istek de ortak kuyrukta bekleyebilir: yoklamanın zaman aşımı, asıl çağrının
öldüğünü göstermez. Sağlık belirsizse asıl çağrı kendi çağrı/tur/boşta sınırları içinde
beklenir; yalnız somut hata yanıtı ya da bağlantı hatası erken kesmeye izin verir.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace

from ...core.types import (
    CompletionRequest,
    Message,
    ModelSpec,
    StreamDone,
    is_rate_limit_error,
)
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


@dataclass(frozen=True, slots=True)
class UnknownHealth:
    """Yoklama asıl çağrının sağlığına dair bağımsız teşhis sağlayamadı."""

    reason: str


#: Üç durum: None → canlı; str → somut hata; UnknownHealth → teşhis yok.
#: Belirsizlikte asıl isteğin mevcut süre sınırları otoritesini korur.
Ping = Callable[[], Awaitable[str | UnknownHealth | None]]
#: Akıştan gelen parça sayısını okuyan fonksiyon (0 → hiç veri gelmedi).
ChunkCount = Callable[[], int]


#: Yerel sunucular isteği tek yuvada sırayla işler. Uzun bir istem (10 bin+ token)
#: işlenirken gelen yoklama kuyrukta bekler ve süresinde cevap alamaz; sunucu "ölü"
#: sanılıp çağrı kesiliyordu (18 Ekim 2026, Ollama + Qwen 9B: ilk çağrı 30. sn'de
#: kesildi, Ollama günlüğünde "client closing the connection").
#
# `llama_cpp`/`llamacpp` de aynı tek yuvalı sınıftadır (A2-16); vLLM isteği toplu
# işler, yoklamaya cevap verebilir ve bu listeye KONMAZ.
_LOCAL_PREFIXES = ("ollama", "ollama_chat", "lm_studio", "llamafile", "llama_cpp", "llamacpp")


def is_api_model(spec: ModelSpec) -> bool:
    """Web oturumu ve yerel modeller yoklanmaz.

    Web: her yoklama bir sohbet açar. Yerel: sunucu tek yuvalıdır, meşgulken yoklamaya
    cevap veremez.
    """
    provider = spec.model.split("/", 1)[0]
    return not provider.endswith("_web") and provider not in _LOCAL_PREFIXES


def ping_for(spec: ModelSpec) -> Ping:
    """Aynı modele, yedek zinciri OLMADAN küçük bir istek gönderen yoklama."""
    yalniz = replace(spec, fallback=())

    async def _ping() -> str | UnknownHealth | None:
        istek = CompletionRequest(
            messages=(Message("user", _PING_TEXT),),
            temperature=0.0,
            max_tokens=16,
            timeout_s=PING_TIMEOUT_S,
        )
        try:
            async with asyncio.timeout(PING_TIMEOUT_S):
                provider = build_provider(yalniz, publisher=None, retry_delays_s=())
                async for item in provider.stream(istek):
                    if isinstance(item, StreamDone):
                        sonuc = item.result
                        if sonuc.ok:
                            return None
                        # 429/aşırı yük yanıtı sunucunun CANLI olduğunu gösterir; "ölü"
                        # sayıp çalışan çağrıyı iptal etmek yanlıştı (A2-16).
                        if is_rate_limit_error(sonuc.error):
                            return None
                        if not sonuc.error:
                            return UnknownHealth("yoklama başarısız; neden belirtilmedi")
                        if any(
                            marker in sonuc.error.lower()
                            for marker in ("timeout", "timed out", "zaman aş", "süre sınır")
                        ):
                            return UnknownHealth("yoklama süre sınırında yanıt üretmedi")
                        return sonuc.error[:160]
        except TimeoutError:
            return UnknownHealth(f"yoklamaya {PING_TIMEOUT_S:.0f} sn içinde cevap yok")
        except ConnectionError as exc:
            return f"yoklama bağlantı hatası: {type(exc).__name__}"
        except Exception as exc:
            # Yerel kurulum/ayrıştırma hatası sunucunun öldüğüne kanıt değildir.
            return UnknownHealth(f"yoklama teşhis üretemedi: {type(exc).__name__}")
        return UnknownHealth("yoklama sonuç üretmeden bitti")

    return _ping


async def watch(chunks: ChunkCount, ping: Ping) -> str:
    """Sessizlik sürdükçe sunucuyu yokla; sağlıksızsa nedenini döndür.

    Akıştan herhangi bir parça (düşünme ya da araç argümanı dahil) gelirse sunucu
    canlıdır ve izleme kendiliğinden biter: sonraki boşlukları parça başı sınır keser.
    Sağlıklı veya belirsiz yoklamada bu korutin dönmez; çağıran, asıl isteğin
    mevcut süre sınırında veya kullanıcı iptalinde bunu da iptal eder.
    """
    await asyncio.sleep(CHECK_AFTER_S)
    while chunks() == 0:
        neden = await ping()
        # Yoklama beklerken gelen asıl parça daha doğrudan canlılık kanıtıdır.
        if chunks() != 0:
            break
        if isinstance(neden, str):
            return neden
        await asyncio.sleep(RECHECK_S)
    await asyncio.Event().wait()  # canlı akış: kapanana kadar bekle (iptal edilir)
    return ""  # pragma: no cover - ulaşılmaz
