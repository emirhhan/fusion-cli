"""Depo haritasının sistem bağlamına girmesi.

`core/repo_map.py` haritayı üretir; bu modül onu hangi bütçeyle ve hangi başlıkla
vereceğimizi tanımlar. Ayrım bilinçlidir: harita üretimi saf ve test edilebilir
kalsın, politika motor katmanında dursun. Haritanın hangi turda ekleneceğine
(`run_agent`: kod kipinde, kök turda) görev türü karar vermez.

Denetlendi (6 Eylül): harita modülü yazılmış ama hiçbir yerden çağrılmıyordu — model
onu hiç görmüyordu. Modülün var olması, Fusion'ın onu kullanabildiği anlamına gelmez.
"""

from __future__ import annotations

from pathlib import Path

from ...core.repo_map import build_repo_map

#: Haritaya ayrılan bağlam bütçesi.
#
# Aider'ın varsayılanı da bu ölçekte: harita YÖNLENDİRİR, dosyanın yerini söyler;
# kodu taşımaz. Büyütmek bağlamı şişirir ve context rot'u hızlandırır.
MAP_BUDGET_CHARS = 1_500


def repo_map_block(root: Path) -> str:
    """Kökte kod varsa başlıklı harita bloğu üret; yoksa boş metin.

    Görev türüne bakılmaz: tür kelime sayımıyla tahmin ediliyordu ve kısa bir
    devam mesajında haritayı düşürüyordu. Harita bütçeyle sınırlıdır; dosyalar
    değişmedikçe metni turdan tura aynıdır ve web sohbetinin öneki kaymaz.
    """
    harita = build_repo_map(root, budget_chars=MAP_BUDGET_CHARS)
    if not harita:
        return ""
    return (
        "# Depo haritası (en çok başvurulan tanımlar)\n"
        "Dosyayı aramadan önce buraya bak; liste kısaltılmıştır, tam değildir.\n"
        f"{harita}"
    )
