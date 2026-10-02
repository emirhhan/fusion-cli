"""Dış dünyaya bakan yeteneklerin sözleşmeleri.

Concrete sınıf iş mantığına gömülmez; motorlar yalnızca bu protokolleri görür.
Böylece sağlayıcı değiştirmek ya da testte sahte vermek imza değişikliği gerektirmez.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Protocol

from .types import CompletionRequest, Message, ModelResult, StreamItem


class LlmProvider(Protocol):
    """Bir LLM'e çağrı yapabilen her şey.

    Uygulamalar hata FIRLATMAZ: kurtarılamayan durumda `ok=False` sonuç döner.
    """

    @property
    def label(self) -> str:
        """Teşhis ve olaylarda kullanılan okunur ad."""
        ...

    async def complete(self, request: CompletionRequest) -> ModelResult:
        """İsteği çalıştır ve toparlanmış sonucu döndür."""
        ...

    def stream(self, request: CompletionRequest) -> AsyncIterator[StreamItem]:
        """İsteği akıtarak çalıştır. Akış daima tek bir `StreamDone` ile biter."""
        ...


class Clock(Protocol):
    """Zaman kaynağı. Testte sahte zaman verilebilmesi için soyutlanmıştır."""

    def monotonic(self) -> float:
        """Süre ölçümü için monoton saniye."""
        ...

    def now(self) -> float:
        """Duvar saati zaman damgası (Unix epoch saniyesi)."""
        ...


class Sleeper(Protocol):
    """Beklemeyi yapan şey. `Clock`'tan AYRIDIR: o zamanı okur, bu zaman geçirir.

    Soyut olmak zorunda: yeniden deneme gecikmeleri 34 ve 68 saniyedir ve testin
    bunları gerçekten beklemesi kabul edilemez — sahte uyutucu beklemeyi kaydeder,
    geçirmez. Aynı sebeple gecikmeler koda gömülmez, yapılandırmadan gelir.
    """

    async def sleep(self, seconds: float) -> None:
        """Verilen süre kadar bekle."""
        ...


class RateLedger(Protocol):
    """Süreçler arası PAYLAŞILAN hız sınırı defteri.

    Masaüstünde her sohbet sekmesi ayrı bir `fusion app` sürecidir; süreç içi
    sağlık kaydı (`HealthRegistry`) ötekilerin 429 aldığını bilmez ve aynı modeli
    yeniden döver. Defter bu bilgiyi bütün süreçlerle paylaşır. Zamanlar duvar
    saatidir (epoch sn): monoton saat süreçler arasında karşılaştırılamaz.
    """

    def cooled_until(self, key: str) -> float:
        """Anahtar bu zamana kadar soğumada; soğumada değilse 0."""
        ...

    def cool(self, key: str, until: float) -> None:
        """Anahtarı `until` anına kadar soğumaya al (daha geç kayıt kısaltılmaz)."""
        ...

    def take_token(self, key: str, per_minute: float) -> float:
        """Dakikalık kovadan bir hak al: alındıysa 0, alınamadıysa beklenecek sn."""
        ...

    def next_index(self, key: str) -> int:
        """Süreçler arası artan sayaç (anahtar havuzunda sıra için)."""
        ...


class TurnJournal(Protocol):
    """Süren bir turun diske yazılan kopyası (çökmeye karşı).

    Masaüstü süreci tur ortasında kapanırsa (çökme, güncelleme, kapanan dizüstü)
    geçmiş yalnız bellekteydi ve "devam et" modele hiçbir şey taşımıyordu. Döngü
    her araç turundan sonra konuşmayı buraya yazar; sekme yeniden açılınca iş
    kaldığı adımdan sürer.
    """

    def save(self, messages: Sequence[Message]) -> None:
        """Turun o ana kadarki mesajlarını yaz (hata fırlatmaz)."""
        ...
