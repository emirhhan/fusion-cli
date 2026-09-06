"""Çapraz dosya tutarlılığı — tek dosya doğru, bütün bozuk.

Ölçüldü (6 Eylül Godot koşusu): `player.gd` `velocity` ve `move_and_slide()`
kullanıyordu (bunlar `CharacterBody2D` API'si), sahnede ise oyuncu düğümü `Area2D`
idi. Her iki dosya KENDİ İÇİNDE geçerliydi; motor açılışta `SCRIPT ERROR: Parse
Error` bastı ve çıkış kodu yine `0` oldu.

Bu sınıf hatayı ne dil kapısı (her dosya geçerli) ne de çalıştırma kapısı (sıfır
çıkış) yakalar. Burada sorulan soru şudur: iki dosya BİRLİKTE tutarlı mı?

Kapsam bilinçli olarak dardır — Godot sahne/script bağı. Genişletmek yeni bir dil
modeli kurmak demektir; dar ve doğru bir denetim, geniş ve tahminî olandan iyidir.
Belirsizlikte SESSİZ kalınır: "extends" bildirmeyen script hakkında uydurma yapılmaz.
"""

from __future__ import annotations

import re
from pathlib import Path

#: Sahnedeki script bağı: `[node ... type="X"]` bloğunda `script = ExtResource("id")`.
_NODE = re.compile(
    r'\[node name="(?P<ad>[^"]+)" type="(?P<tip>[^"]+)"[^\]]*\]\n(?P<govde>(?:(?!\[node)[\s\S])*)'
)
_EXT_RESOURCE = re.compile(
    r'\[ext_resource type="Script" path="(?P<path>[^"]+)" id="(?P<id>[^"]+)"'
)
_SCRIPT_REF = re.compile(r'script\s*=\s*ExtResource\("(?P<id>[^"]+)"\)')
_EXTENDS = re.compile(r"^extends\s+(?P<taban>[A-Za-z_][\w]*)", re.MULTILINE)

#: Godot düğüm tipi → o tipin miras aldığı üst tipler.
#
# Tam sınıf ağacı değildir ve olmamalıdır: yalnız ölçülen çatışmayı (fizik gövdesi
# API'sini Area2D düğümüne bağlamak) yakalayacak kadar dardır.
_INHERITS: dict[str, frozenset[str]] = {
    "CharacterBody2D": frozenset(
        {"CharacterBody2D", "PhysicsBody2D", "CollisionObject2D", "Node2D", "Node"}
    ),
    "RigidBody2D": frozenset(
        {"RigidBody2D", "PhysicsBody2D", "CollisionObject2D", "Node2D", "Node"}
    ),
    "StaticBody2D": frozenset(
        {"StaticBody2D", "PhysicsBody2D", "CollisionObject2D", "Node2D", "Node"}
    ),
    "Area2D": frozenset({"Area2D", "CollisionObject2D", "Node2D", "Node"}),
    "Node2D": frozenset({"Node2D", "Node"}),
    "Sprite2D": frozenset({"Sprite2D", "Node2D", "Node"}),
    "Node": frozenset({"Node"}),
}


def scene_script_conflicts(root: Path) -> tuple[str, ...]:
    """Sahnedeki düğüm tipi ile bağlı script'in tabanı çelişiyor mu?"""
    bulgular: list[str] = []
    for sahne in sorted(root.rglob("*.tscn")):
        bulgular.extend(_conflicts_in_scene(sahne, root))
    return tuple(bulgular)


def _conflicts_in_scene(sahne: Path, root: Path) -> list[str]:
    try:
        metin = sahne.read_text(encoding="utf-8")
    except OSError:
        return []
    kaynaklar = {
        eslesme.group("id"): eslesme.group("path") for eslesme in _EXT_RESOURCE.finditer(metin)
    }
    if not kaynaklar:
        return []
    bulgular: list[str] = []
    for dugum in _NODE.finditer(metin):
        ref = _SCRIPT_REF.search(dugum.group("govde"))
        if ref is None:
            continue
        yol = kaynaklar.get(ref.group("id"))
        if not yol:
            continue
        taban = _script_base(root, yol)
        if taban is None:
            continue
        tip = dugum.group("tip")
        beklenen = _INHERITS.get(tip)
        if beklenen is None or taban in beklenen:
            continue
        bulgular.append(
            f"{sahne.name}: '{dugum.group('ad')}' düğümü {tip} tipinde ama bağlı script "
            f"({Path(str(yol)).name}) {taban} bekliyor; motor açılışta parse hatası verir."
        )
    return bulgular


def _script_base(root: Path, res_path: str) -> str | None:
    """Script'in `extends` tabanını oku; bildirilmemişse `None` (uydurma yapma)."""
    goreli = res_path.removeprefix("res://")
    dosya = root / goreli
    try:
        kaynak = dosya.read_text(encoding="utf-8")
    except OSError:
        return None
    eslesme = _EXTENDS.search(kaynak)
    return eslesme.group("taban") if eslesme else None
