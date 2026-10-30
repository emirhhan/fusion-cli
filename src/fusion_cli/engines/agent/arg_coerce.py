"""Zayıf modellerin araç argümanlarında yaptığı tip kaymalarını güvenle onar (A1-22).

Ölçüldü (30 Ekim): `required:"true"`, `offset:"0"`, `width:"1920"` ya da `1920.0`
gelince araçlar boş döner ya da hata verirdi; her ret bir onarım hakkı yakar. Onarım
YALNIZ kayıpsız dönüşümlerdir (tam sayı değerli metin/ondalık, "true"/"false"); belirsiz
değer (`"abc"`, `1.5`, `True` sayı yerine) olduğu gibi bırakılır ve çağıran hata verir.
"""

from __future__ import annotations

import json

_TRUE = frozenset({"true", "evet", "yes", "1"})
_FALSE = frozenset({"false", "hayır", "hayir", "no", "0"})


def coerce_int(value: object) -> object:
    """Kayıpsız tam sayıya çevrilebiliyorsa `int`, değilse girdiyi aynen döndür."""
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        metin = value.strip()
        try:
            return int(metin)
        except ValueError:
            try:
                ondalik = float(metin)
            except ValueError:
                return value
            return int(ondalik) if ondalik.is_integer() else value
    return value


def coerce_bool(value: object) -> object:
    """ "true"/"false" metnini `bool` yap; tanınmayan değeri aynen döndür."""
    if isinstance(value, str):
        metin = value.strip().casefold()
        if metin in _TRUE:
            return True
        if metin in _FALSE:
            return False
    return value


def coerce_list(value: object) -> object:
    """JSON metni olarak gelen listeyi aç; liste değilse girdiyi aynen döndür."""
    if isinstance(value, str):
        try:
            acilmis = json.loads(value)
        except ValueError:
            return value
        return acilmis if isinstance(acilmis, list) else value
    return value
