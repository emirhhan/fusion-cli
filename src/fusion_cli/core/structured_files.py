"""Yapısal dosya biçimlerinin yazılmadan ÖNCE denetlenmesi.

Neden gerekli: model bilmediği bir biçimi elle düzenlediğinde dosya sessizce
bozuluyor ve tur "tamamlandı" diye kapanıyor. Ölçülen vaka Godot'tu — model MCP
aracıyla tıkanınca `.tscn` dosyasını `replace_range` ile düzenledi, sahne
formatını bilmediği için başlığı sildi ve Godot `Parse Error: Unrecognized file
type 'node'` verdi. Kullanıcı "tamamlandı" mesajıyla birlikte bozuk bir proje
aldı.

Denetim BİÇİM tanır, dosya adı değil: aynı hata `.json`, `.toml` ve Godot kaynak
dosyalarında aynı biçimde ortaya çıkıyor. Yeni bir biçim eklemek `_DENETLEYICILER`
tablosuna bir satır eklemektir.

`core` katmanındadır ve üçüncü partiye bağımlı DEĞİLDİR (RULES.md "Katman
Sınırları"): denetim dosya yazan her yerden çağrılabilmelidir.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Callable
from pathlib import Path

__all__ = ["validate_structured"]

#: `[bolum]` biçimindeki bölüm başlığı.
_BOLUM = re.compile(r"^\[(?P<ad>[^\]\s]+)")


def _anlamli_satirlar(content: str) -> list[str]:
    """Yorum ve boş satırlar atılmış, kırpılmış satırlar."""
    return [
        satir.strip()
        for satir in content.splitlines()
        if satir.strip() and not satir.lstrip().startswith((";", "#"))
    ]


def _json_denetle(content: str) -> str | None:
    try:
        json.loads(content)
    except ValueError as hata:
        return f"Geçersiz JSON: {hata}"
    return None


def _toml_denetle(content: str) -> str | None:
    try:
        tomllib.loads(content)
    except (ValueError, tomllib.TOMLDecodeError) as hata:
        return f"Geçersiz TOML: {hata}"
    return None


def _godot_kaynak_denetle(content: str) -> str | None:
    """Godot metin kaynağı (`.tscn`, `.tres`).

    İki kural ÖLÇÜLDÜ, uydurulmadı:
    1. Dosya `[gd_scene …]` ya da `[gd_resource …]` ile başlamalı; başlıksız
       dosyada Godot "Unrecognized file type" veriyor.
    2. `[ext_resource …]` blokları düğümlerden ÖNCE gelmeli; sonra yazıldığında
       sahne yüklenmiyor.
    """
    satirlar = _anlamli_satirlar(content)
    if not satirlar:
        return "Godot kaynak dosyası boş olamaz; `[gd_scene format=3]` ile başlamalı."
    ilk = _BOLUM.match(satirlar[0])
    if ilk is None or ilk.group("ad") not in {"gd_scene", "gd_resource"}:
        return (
            "Godot kaynak dosyası `[gd_scene format=3]` (sahne) ya da "
            "`[gd_resource …]` (kaynak) satırıyla BAŞLAMALI. Bu başlık olmadan "
            "Godot dosyayı tanımaz: `Parse Error: Unrecognized file type`."
        )
    dugum_goruldu = False
    for satir in satirlar:
        eslesme = _BOLUM.match(satir)
        if eslesme is None:
            continue
        ad = eslesme.group("ad")
        if ad == "node":
            dugum_goruldu = True
        elif ad == "ext_resource" and dugum_goruldu:
            return (
                "`[ext_resource …]` blokları TÜM `[node …]` bloklarından ÖNCE "
                "gelmeli. Sonra yazıldığında Godot kaynakları çözemez ve sahne "
                "yüklenmez."
            )
    return None


def _godot_proje_denetle(content: str) -> str | None:
    """`project.godot` — anahtarlar bir bölüm başlığından SONRA gelmeli.

    Ölçüldü: bölümsüz yazılan `run/main_scene` görmezden geliniyor ve Godot
    "no main scene defined in the project" diyor.
    """
    for satir in _anlamli_satirlar(content):
        if _BOLUM.match(satir):
            return None
        if "=" in satir:
            # Düzeltme TARİF EDİLMEZ, GÖSTERİLİR: ölçüldü, model tarifi okuyup
            # aynı içeriği üç kez yeniden gönderdi. Mekanik bir talimat
            # ("şu satırı en başa ekle") uygulanabilir olandır.
            return (
                "`project.godot` içindeki anahtarlar bir bölüm başlığından SONRA "
                "gelmeli; bölümsüz anahtarlar görmezden gelinir ve Godot "
                "`no main scene defined in the project` der.\n"
                "DÜZELTME: dosyanın EN BAŞINA `[application]` satırını ekle. "
                f"Yani ilk satır `[application]`, ikinci satır `{satir}` olsun."
            )
    return None


#: Uzantı → denetleyici. Yeni biçim eklemek buraya bir satır eklemektir.
_DENETLEYICILER: dict[str, Callable[[str], str | None]] = {
    ".json": _json_denetle,
    ".toml": _toml_denetle,
    ".tscn": _godot_kaynak_denetle,
    ".tres": _godot_kaynak_denetle,
}

#: Uzantısı değil ADI belirleyici olan dosyalar.
_ADA_GORE: dict[str, Callable[[str], str | None]] = {
    "project.godot": _godot_proje_denetle,
}


def validate_structured(path: Path, content: str) -> str | None:
    """İçerik bu biçim için geçerli mi? Sorun varsa AÇIKLAMASI, yoksa `None`.

    Bilinmeyen biçimde `None` döner: denetlemediğimiz bir dosyayı reddetmek,
    modeli yapamayacağı bir düzeltmeye zorlardı.
    """
    denetleyici = _ADA_GORE.get(path.name) or _DENETLEYICILER.get(path.suffix.casefold())
    return denetleyici(content) if denetleyici else None
