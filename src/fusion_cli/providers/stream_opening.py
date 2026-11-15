"""Sağlayıcı akışının ilk gerçek çıktısını bulurken canlılık parçalarını elde tut.

Boş geçici parça (`TextChunk("", provisional=True)`) yanıtın başladığı anlamına gelmez
ama modelin ÇALIŞTIĞINI söyler (araç argümanı yazıyor, düşünüyor). Ölçüldü (29 Ekim):
eski `first_meaningful` bu parçaları tüketip atıyordu; yalnızca araç çağrısından oluşan
uzun bir yanıtta üst katman (`loop._call_model`, `_observe_stream_item`) hiçbir canlılık
parçası görmüyor, sunucu yoklaması ve sessizlik izlemesi yanlış karar verebiliyordu
(P1-05). Sarmalayıcılar artık bu parçaları GELDİKÇE ileten döngüyü kendileri yürütür;
karar tek yerde (`is_liveness_chunk`) durur.
"""

from __future__ import annotations

from ..core.types import StreamItem, TextChunk


def is_liveness_chunk(item: StreamItem | None) -> bool:
    """Bu öğe yalnızca "model çalışıyor" işareti mi (yanıtın başlangıcı değil)?"""
    return isinstance(item, TextChunk) and item.provisional and not item.text


def is_provisional(item: StreamItem | None) -> bool:
    """Geçici parça mı: yanıtın başladığını göstermez, atlanıp bir sonraki öğeye bakılır.

    Metin taşıyan geçici parça (öncü beyan/düşünce) başarısız bir sağlayıcıdan sonra
    yedeğe geçilirken ekrana sızmamalıdır; yalnız BOŞ canlılık parçaları iletilir.
    """
    return isinstance(item, TextChunk) and item.provisional
