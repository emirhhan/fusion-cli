"""İstem şablonunda `{ad}` yer tutucularını TEK GEÇİŞTE doldur.

Zincirleme `.replace("{task}", …).replace("{trace}", …)` bir yer tutucunun değerinde
geçen başka bir yer tutucuyu (`{trace}`) bir sonraki çağrıda yeniden doldurur: kullanıcı
görevinde geçen `{trace}` yazısı tüm iz metnini göreve gömerdi. Ölçüldü (30 Ekim).
`str.format` de kullanılmaz: şablonlardaki JSON örnekleri süslü parantez içerir.
"""

from __future__ import annotations

import re
from collections.abc import Mapping


def fill_template(template: str, values: Mapping[str, str]) -> str:
    """Yalnız `values` anahtarlarına karşılık gelen `{anahtar}` yer tutucularını doldur."""
    if not values:
        return template
    desen = re.compile(r"\{(" + "|".join(re.escape(anahtar) for anahtar in values) + r")\}")
    return desen.sub(lambda eslesme: values[eslesme.group(1)], template)
