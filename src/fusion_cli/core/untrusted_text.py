"""Güvenilmez metni etiketli bloğa sarma: kapanış etiketi kaçırılamaz (P-048, P-060).

Başka oturumdan gelen mesaj, arka plan görevinin sonucu gibi metinler modele etiketli
blok içinde gider. İçerik bloğun kapanış etiketini taşırsa etiketin dışına "kaçan" metin
güvenilir görünürdü; burada kapanış etiketleri büyük/küçük harf ve boşluk varyantlarıyla
birlikte etkisizleştirilir. Ölçüldü (31 Ekim): `core/peers.py` yalnız tam yazımı, arka plan
işçisi hiçbirini kaçırmıyordu.
"""

from __future__ import annotations

import re


def neutralize_closing_tags(text: str, *tags: str) -> str:
    """`</etiket>` biçimlerini (`</ ETIKET >` dahil) `&lt;/etiket&gt;` yapar.

    Kaçış biçimi hiçbir kapanış varyantına uymaz (eski `</ etiket>` biçimi esnek bir
    okuyucuya göre yine kapanıştı); açılış etiketlerine dokunulmaz.
    """
    for tag in tags:
        pattern = re.compile(rf"<\s*/\s*{re.escape(tag)}\s*>", re.IGNORECASE)
        text = pattern.sub(f"&lt;/{tag}&gt;", text)
    return text
