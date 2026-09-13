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


#: Çalışma anında script üretip düğüme bağlama kalıbı.
_RUNTIME_SCRIPT = re.compile(r"GDScript\.new\s*\(")
_SET_SCRIPT = re.compile(r"\.set_script\s*\(")
_RELOAD = re.compile(r"\.reload\s*\(")

#: Kullanıcıya "şu tuşla oynanır" diyen metinlerdeki harf çifti (ör. "A/D").
_PROMISED_KEYS = re.compile(r"\b([A-Z])/([A-Z])\b")
#: Koddan doğrudan okunan fiziksel tuş.
_KEY_CONSTANT = re.compile(r"KEY_([A-Z])\b")
#: `project.godot` içindeki girdi eşlemesi bölümü.
_INPUT_SECTION = re.compile(r"^\s*\[input\]", re.MULTILINE)


def runtime_script_conflicts(root: Path) -> tuple[str, ...]:
    """Çalışma anında üretilen script `reload()` edilmeden bağlanmış mı?

    Godot'ta `GDScript.new()` ile üretilen bir script, `reload()` çağrılmadan
    `set_script()` ile bağlanırsa DERLENMEZ: motor hiçbir hata basmaz, düğüm
    sessizce ölü kalır.

    Ölçüldü (13 Eylül, Godot koşusu): oyuncu düğümünün hareket/zıplama kodu tam da
    bu yolla üretildi. Motor sıfır çıkışla açıldı, kapılar geçti, kullanıcı oyunu
    açtı ve karakter hiçbir tuşa cevap vermedi. Aynı kalıbı `reload()` ile ve
    onsuz iki kez ölçtüm: yalnız `reload()` olan çalıştı.
    """
    bulgular: list[str] = []
    for kaynak in sorted(root.rglob("*.gd")):
        try:
            metin = kaynak.read_text(encoding="utf-8")
        except OSError:
            continue
        if not _RUNTIME_SCRIPT.search(metin) or not _SET_SCRIPT.search(metin):
            continue
        if _RELOAD.search(metin):
            continue
        bulgular.append(
            f"{kaynak.name}: çalışma anında üretilen GDScript `reload()` edilmeden "
            "`set_script()` ile bağlanıyor; script derlenmez ve düğüm sessizce ölü "
            "kalır. `source_code` atadıktan SONRA `script.reload()` çağır."
        )
    return tuple(bulgular)


def promised_key_conflicts(root: Path) -> tuple[str, ...]:
    """Arayüzde söz verilen tuşlar gerçekten bağlanmış mı?

    Ölçüldü (13 Eylül, Godot koşusu): oyunun HUD'u "[HAREKET: A/D veya OKLAR]"
    yazıyordu; `project.godot` içinde hiç `[input]` bölümü yoktu ve kod yalnız
    yerleşik `ui_*` eylemlerini okuyordu. Kullanıcı A/D'ye bastı, hiçbir şey olmadı.
    Kullanıcıya gösterilen tuş, bağlanmamış tuş olamaz.

    Kapı DAR: proje bir girdi eşlemesi tanımlıyorsa sessiz kalır (eşlemenin içeriği
    burada çözülmez), yalnız hiç eşleme yokken söz verilen harfleri bildirir.
    """
    proje = root / "project.godot"
    try:
        yapilandirma = proje.read_text(encoding="utf-8")
    except OSError:
        return ()
    if _INPUT_SECTION.search(yapilandirma):
        return ()
    sozler: dict[str, str] = {}
    okunan: set[str] = set()
    for kaynak in sorted([*root.rglob("*.gd"), *root.rglob("*.tscn")]):
        try:
            metin = kaynak.read_text(encoding="utf-8")
        except OSError:
            continue
        okunan.update(_KEY_CONSTANT.findall(metin))
        for eslesme in _PROMISED_KEYS.finditer(metin):
            for harf in eslesme.groups():
                sozler.setdefault(harf, kaynak.name)
    eksik = sorted(harf for harf in sozler if harf not in okunan)
    if not eksik:
        return ()
    return (
        "arayüz " + ", ".join(eksik) + " tuşlarıyla oynandığını söylüyor ama "
        "project.godot içinde hiç girdi eşlemesi ([input]) yok ve kod bu tuşları "
        "okumuyor; oyun o tuşlara cevap vermez.",
    )


#: Script'in sahnede VAR OLMASINI beklediği çocuk düğüm: `$Ad` ya da `get_node("Ad")`.
# Yol içeren referans (`$UI/Label`) DIŞARIDA: çok parçalı yol hakkında iddia
# edilmez, kapı dar kalır.
_CHILD_REF = re.compile(
    r'(?:\$(?P<kisa>[A-Za-z_]\w*)(?![\w/])|get_node\(\s*"(?P<uzun>[^"/]+)"\s*\))'
)
#: Sahnedeki düğümün adı ve ebeveyni.
_NODE_HEADER = re.compile(
    r'\[node name="(?P<ad>[^"]+)"(?:[^\]]*?parent="(?P<ebeveyn>[^"]*)")?[^\]]*\]'
)


def missing_node_references(root: Path) -> tuple[str, ...]:
    """Script'in beklediği çocuk düğüm sahnede var mı?

    `@onready var sprite = $Sprite2D` satırı, sahnede `Sprite2D` adlı bir çocuk
    YOKSA `null` döner. Godot açılışta hiçbir şey söylemez; oyun ilk kullanımda
    (ör. ilk harekette `sprite.flip_h`) çöker ya da sessizce hiçbir şey yapmaz.

    Ölçüldü (13 Eylül, koşu 26): `player.gd` `$Sprite2D` bekliyordu, `main.tscn`
    içindeki Player düğümünün tek çocuğu `CollisionShape2D` idi. Proje başsız
    açıldı, bütün kapılar geçti, oyun "tamamlandı" raporlandı.

    Kapı DAR: yalnız tek parçalı adlar (`$Sprite2D`) denetlenir; yol içeren
    (`$UI/Label`) ya da çalışma anında eklenen düğümler hakkında iddia edilmez.
    """
    bulgular: list[str] = []
    for sahne in sorted(root.rglob("*.tscn")):
        try:
            metin = sahne.read_text(encoding="utf-8")
        except OSError:
            continue
        kaynaklar = {
            eslesme.group("id"): eslesme.group("path")
            for eslesme in _EXT_RESOURCE.finditer(metin)
        }
        for dugum in _NODE.finditer(metin):
            ref = _SCRIPT_REF.search(dugum.group("govde"))
            if ref is None:
                continue
            yol = kaynaklar.get(ref.group("id"))
            if yol is None:
                continue
            cocuklar = _children_of(metin, _scene_path(metin, dugum.group("ad")))
            bulgular.extend(
                f"{sahne.name}: '{dugum.group('ad')}' düğümüne bağlı "
                f"{Path(yol).name} script'i `${beklenen}` düğümünü kullanıyor ama sahnede "
                "o adda bir çocuk yok; değişken null olur ve oyun ilk kullanımda çöker."
                for beklenen in _expected_children(root, yol) - cocuklar
            )
    return tuple(bulgular)


def _scene_path(metin: str, ad: str) -> str:
    """Düğümün sahne içindeki YOLU: çocukları bu yolu `parent` olarak yazar.

    Kök düğümün `parent` alanı yoktur ve çocukları `parent="."` yazar; ara bir
    düğümün çocukları ise `parent="Ust/Ad"` yazar. Ölçüldü (13 Eylül): kontrol
    `parent="Main"` arıyordu, gerçek sahnede kökün çocukları `parent="."` yazıyordu
    ve kapı VAR OLAN düğümü yok sanıp bitmiş bir sahneyi reddediyordu.
    """
    for eslesme in _NODE_HEADER.finditer(metin):
        if eslesme.group("ad") != ad:
            continue
        ebeveyn = eslesme.group("ebeveyn")
        if ebeveyn is None:
            return "."
        return ad if ebeveyn == "." else f"{ebeveyn}/{ad}"
    return ad


def _children_of(metin: str, yol: str) -> set[str]:
    """Sahne metninde `yol` düğümünün doğrudan çocuklarının adları."""
    return {
        eslesme.group("ad")
        for eslesme in _NODE_HEADER.finditer(metin)
        if (eslesme.group("ebeveyn") or "") == yol
    }


#: Düğümün YOKLUĞUNA karşı korunan erişim: `has_node("X")`, `get_node_or_null("X")`.
_GUARDED_REF = re.compile(
    r'(?:has_node|get_node_or_null)\(\s*"(?P<ad>[^"]+)"\s*\)'
)


def _expected_children(root: Path, res_path: str) -> set[str]:
    """Script'in VARLIĞINA GÜVENDİĞİ tek parçalı çocuk düğümler.

    `has_node("X")` ya da `get_node_or_null("X")` ile korunan erişim eksik düğümde
    çökmez; onu suçlamak bitmiş bir sahneyi reddetmek olur. Ölçüldü (13 Eylül):
    `ui_manager.gd` tüm erişimlerini `has_node` ile koruyordu ve kapı yine de
    "eksik düğüm" diyordu.
    """
    dosya = root / res_path.removeprefix("res://")
    try:
        kaynak = dosya.read_text(encoding="utf-8")
    except OSError:
        return set()
    korunan = {
        ad.split("/")[0] for ad in (e.group("ad") for e in _GUARDED_REF.finditer(kaynak))
    }
    beklenen = {
        eslesme.group("kisa") or eslesme.group("uzun")
        for eslesme in _CHILD_REF.finditer(kaynak)
    }
    return {ad for ad in beklenen if ad not in korunan}


#: Kodda ya da sahnede geçen proje içi kaynak yolu.
_RES_PATH = re.compile(r'res://(?P<yol>[^"\')\n]+)')
#: Düğüm API'si kullanan ama tabanını bildirmeyen script'in izleri.
_NODE_API = re.compile(r"\b(?:move_and_slide|is_on_floor|velocity|add_child|queue_free)\b")


def broken_resource_paths(root: Path) -> tuple[str, ...]:
    """Kodun/sahnenin yüklediği `res://` yolu diskte gerçekten var mı?

    Ölçüldü (13 Eylül, koşu 28): indirilen paket
    `assets/Grassland Platformer Art **With Slopes**/` klasörüne açıldı (ad
    yıldızlı), kod ise yıldızsız yolu yüklüyordu. `ResourceLoader.exists()` false
    döndü, hiçbir doku yüklenmedi ve motor tek satır hata basmadı — kapılar geçti,
    koşu "tamamlandı" dedi ve oyun bomboş açıldı.

    Kapı DAR: yalnız değişmez (sabit) yollar denetlenir; içinde biçimlendirme ya
    da birleştirme olan ifadeler hakkında iddia edilmez.
    """
    bulgular: list[str] = []
    # `project.godot` DAHİL: projenin en kritik `res://` yolu ana sahnedir.
    #
    # Ölçüldü (13 Eylül, koşu 32): `run/main_scene="res://scenes/main.tscn"` yazıyordu
    # ama dosya hiç yazılmamıştı. Godot üç satır ERROR bastı ve ÇIKIŞ KODU 0 verdi;
    # kapılar geçti, koşu teslim aşamasına geldi. Hatayı ancak öz denetim gördü.
    kaynaklar = [
        *root.rglob("*.gd"),
        *root.rglob("*.tscn"),
        *root.rglob("*.tres"),
        *([root / "project.godot"] if (root / "project.godot").is_file() else []),
    ]
    for kaynak in sorted(kaynaklar):
        if any(part.startswith(".") for part in kaynak.parts):
            continue
        try:
            metin = kaynak.read_text(encoding="utf-8")
        except OSError:
            continue
        for eslesme in _RES_PATH.finditer(metin):
            yol = eslesme.group("yol").strip()
            if not yol or "%" in yol or "{" in yol or yol.endswith("/"):
                continue
            if (root / yol).exists():
                continue
            bulgular.append(
                f"{kaynak.name}: `res://{yol}` yolu diskte YOK; yükleme sessizce "
                "başarısız olur. Gerçek yolu `list_dir` ile doğrula ve düzelt."
            )
    return tuple(dict.fromkeys(bulgular))


def scripts_without_base(root: Path) -> tuple[str, ...]:
    """Düğüm API'si kullanan script tabanını (`extends`) bildiriyor mu?

    `extends` satırı olmayan bir GDScript `RefCounted` sayılır; `velocity`,
    `move_and_slide()` gibi düğüm üyeleri orada YOKTUR.

    Ölçüldü (13 Eylül, koşu 28): `player.gd` `const SPEED` ile başlıyordu, hiç
    `extends` yoktu ve `velocity`/`move_and_slide()` kullanıyordu. Dosya hiçbir
    sahneye bağlı olmadığı için motor da sessiz kaldı; proje açıldı, kapılar geçti
    ve oyunda oyuncu diye bir şey yoktu.
    """
    bulgular: list[str] = []
    for kaynak in sorted(root.rglob("*.gd")):
        if any(part.startswith(".") for part in kaynak.parts):
            continue
        try:
            metin = kaynak.read_text(encoding="utf-8")
        except OSError:
            continue
        if _EXTENDS.search(metin) or not _NODE_API.search(metin):
            continue
        bulgular.append(
            f"{kaynak.name}: düğüm API'si (velocity/move_and_slide gibi) kullanıyor "
            "ama `extends` satırı yok; script RefCounted sayılır ve bu üyeler orada "
            "bulunmaz. Dosyanın başına doğru tabanı yaz (ör. `extends CharacterBody2D`)."
        )
    return tuple(bulgular)
