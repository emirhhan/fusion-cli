"""`Araç(parametre:değer)` kuralı: deny ve ask için üst düzey parametre eşlemesi (#80).

Claude Code (code.claude.com/docs/en/permissions#match-by-input-parameter):

* Yalnız deny ve ask; allow kuralı her aracın kendi belirteç sözdizimini kullanır.
* Parametre aracın girdisinin doğrudan alanıdır; iç içe alan eşlenmez. Model alanı hiç
  göndermediyse kural eşleşmez. Değer birebir karşılaştırılır, `*` her metni karşılar.
* İki nokta çevresindeki boşluk yok sayılır.
* Birincil içerik alanı (`command`, `file_path`, `path`, `notebook_path`, `url`) bu yolla
  eşlenemez: kural yok sayılır (bileşik komutla atlatılabilirdi).

Kural yalnız parametre adı çağrının girdisinde VARSA parametre kuralı sayılır; yoksa
belirteç aracın kendi sözdizimiyle okunur (ör. `Bash(ls:*)` sondaki-yıldız yazımıdır).
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from ..config.permission_rules import PermissionDecision, PermissionRule

_PARAM_SPEC = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*?)\s*$", re.DOTALL)
#: Bu yolla eşlenemeyen birincil içerik alanları.
PRIMARY_CONTENT_FIELDS = frozenset({"command", "file_path", "path", "notebook_path", "url"})


def param_rule_verdict(rule: PermissionRule, args: Mapping[str, object]) -> bool | None:
    """Parametre kuralıysa eşleşme sonucu; değilse `None` (olağan eşlemeye düşülür)."""
    if rule.decision is PermissionDecision.ALLOW or not rule.specifier:
        return None
    if rule.specifier.startswith("domain:"):
        return None
    found = _PARAM_SPEC.match(rule.specifier)
    if found is None:
        return None
    name, expected = found.group(1), found.group(2)
    if name in PRIMARY_CONTENT_FIELDS:
        return False
    if name not in args:
        return None
    return _value_matches(expected, args[name])


def _value_matches(expected: str, value: object) -> bool:
    if isinstance(value, (Mapping, list, tuple)) or value is None:
        return False
    text = str(value).lower() if isinstance(value, bool) else str(value)
    if "*" not in expected:
        return text == expected
    regex = ".*".join(re.escape(part) for part in expected.split("*"))
    return re.fullmatch(regex, text, re.DOTALL) is not None
