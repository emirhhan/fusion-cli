"""`--settings` izin kuralları katmanı (#296) — Claude'un "command line arguments" kaynağı.

Claude Code'da `claude --settings <dosya|json>` içindeki `permissions.allow/ask/deny`
kuralları oturum boyunca öteki ayar katmanlarıyla birlikte değerlendirilir (en kısıtlayıcı
kazanır). Fusion'da kök komut bu bloğu süreç ortamına (`FUSION_FLAG_PERMISSIONS`, JSON)
yazar; `load_permission_rules` her okumada bu katmanı da ekler. Böylece etkileşimli oturum,
aynı süreçteki alt ajanlar ve oturumdan başlatılan alt süreçler aynı kuralları görür.

Katman kullanıcının komut satırında AÇIKÇA verdiği değerdir: güven denetimi gerekmez ve
`--setting-sources` süzmesine girmez (Claude: `--settings` her zaman yüklenir).
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping

from .permission_rules import PermissionDecision, PermissionRule, parse_rule

FLAG_PERMISSIONS_ENV = "FUSION_FLAG_PERMISSIONS"
#: İzin katmanı adı (`/permissions` görünümünde kaynak olarak gösterilir).
LAYER_FLAG = "bayrak"


def set_flag_permissions(permissions: Mapping[str, object] | None) -> None:
    """`--settings` `permissions` bloğunun kural listelerini bu süreç için ayarla."""
    lists = {
        decision.value: [e for e in entries if isinstance(e, str)]
        for decision in PermissionDecision
        if permissions is not None and isinstance(entries := permissions.get(decision.value), list)
    }
    if not any(lists.values()):
        os.environ.pop(FLAG_PERMISSIONS_ENV, None)
        return
    os.environ[FLAG_PERMISSIONS_ENV] = json.dumps(lists, ensure_ascii=False)


def flag_permission_rules() -> tuple[PermissionRule, ...]:
    """Ortamdaki `--settings` kuralları; değişken yoksa ya da bozuksa boş."""
    raw = os.environ.get(FLAG_PERMISSIONS_ENV)
    if not raw:
        return ()
    try:
        data = json.loads(raw)
    except ValueError:
        return ()
    if not isinstance(data, dict):
        return ()
    found: list[PermissionRule] = []
    for decision in PermissionDecision:
        entries = data.get(decision.value)
        if not isinstance(entries, list):
            continue
        found.extend(
            rule for entry in entries if (rule := parse_rule(entry, decision, source=LAYER_FLAG))
        )
    return tuple(found)
