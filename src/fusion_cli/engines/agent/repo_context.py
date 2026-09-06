"""Depo haritasının sistem bağlamına girmesi.

`core/repo_map.py` haritayı üretir; bu modül onu NE ZAMAN vereceğimize karar verir.
Ayrım bilinçlidir: harita üretimi saf ve test edilebilir kalsın, politika (hangi
görev türü hak ediyor, hangi bütçeyle) motor katmanında dursun.

Denetlendi (6 Eylül): harita modülü yazılmış ama hiçbir yerden çağrılmıyordu — model
onu hiç görmüyordu. Modülün var olması, Fusion'ın onu kullanabildiği anlamına gelmez.
"""

from __future__ import annotations

from pathlib import Path

from ...core.repo_map import build_repo_map
from .classify import TaskKind
from .loops import wants_plan

#: Haritaya ayrılan bağlam bütçesi.
#
# Aider'ın varsayılanı da bu ölçekte: harita YÖNLENDİRİR, dosyanın yerini söyler;
# kodu taşımaz. Büyütmek bağlamı şişirir ve context rot'u hızlandırır.
MAP_BUDGET_CHARS = 1_500


def repo_map_block(root: Path, kind: TaskKind) -> str:
    """Görev haritayı hak ediyorsa başlıklı blok üret; yoksa boş metin.

    Yalnız çok adımlı işlerde eklenir: "merhaba" sorusuna sembol listesi iliştirmek
    bağlamı boşuna şişirir ve ölçülen kayıp tam da budur (context rot).
    """
    if not wants_plan(kind):
        return ""
    harita = build_repo_map(root, budget_chars=MAP_BUDGET_CHARS)
    if not harita:
        return ""
    return (
        "# Depo haritası (en çok başvurulan tanımlar)\n"
        "Dosyayı aramadan önce buraya bak; liste kısaltılmıştır, tam değildir.\n"
        f"{harita}"
    )
