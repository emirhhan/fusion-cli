"""Çok-hesap anahtar toplama — bir sağlayıcı için BİRDEN ÇOK anahtar.

Kullanıcı aynı sağlayıcının birkaç (ücretsiz) hesabını üst üste yığabilir: biri
hız sınırına takılınca istek ötekine kayar. Anahtarlar ortamdan iki biçimde alınır:

- **Numaralı sonek**: `OPENROUTER_API_KEY`, `OPENROUTER_API_KEY_2`, `..._3`, …
- **Virgülle ayrılmış**: `OPENROUTER_API_KEY=key1,key2,key3`

İkisi birlikte de kullanılabilir. Boşlar atlanır, tekrarlar (aynı anahtar) elenir,
sıra korunur. Ortam erişimi config katmanındadır (RULES).
"""

from __future__ import annotations

from collections.abc import Mapping

#: Numaralı sonek taraması bu değere kadar gider (_2 .. _MAX). Makul üst sınır;
#: kimse bir sağlayıcıya yirmi hesap bağlamaz, ama sınır sabit ve merkezîdir.
_MAX_NUMBERED = 20


def _split(value: str) -> list[str]:
    """Virgülle ayrılmış anahtar dizesini temiz parçalara böl."""
    return [part.strip() for part in value.split(",") if part.strip()]


def collect_keys(env_name: str, environ: Mapping[str, str]) -> tuple[str, ...]:
    """Bir sağlayıcının tüm anahtarlarını ortamdan topla (sıra korunur, tekrar elenir)."""
    keys: list[str] = []
    keys.extend(_split(environ.get(env_name, "")))
    for index in range(2, _MAX_NUMBERED + 1):
        keys.extend(_split(environ.get(f"{env_name}_{index}", "")))
    # Tekrarları ele, ilk görülen sırayı koru.
    return tuple(dict.fromkeys(keys))
