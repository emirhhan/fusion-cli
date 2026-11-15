"""`yetenek.gorunurluk` RPC'si: masaüstünden beceri görünürlüğü `skillOverrides`'a (#176).

Veri: `{"ad": "<beceri adı>", "gorunurluk": "on|name-only|user-invocable-only|off"}`;
`gorunurluk` verilmezse ya da `"dongu"` ise sıradaki değere geçilir (panelin Enter'ı).
Kayıt terminal/TUI paneliyle aynı işlevden geçer (`skills_panel.save_changes`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..cli.repl import skills_panel
from ..cli.repl.state import ReplState
from ..config.models import SkillVisibility
from ..config.skill_overrides_writer import next_visibility


def list_skill_visibility(state: ReplState) -> dict[str, Any]:
    """`yetenek.gorunurluk_listesi`: masaüstü `/skills` liste paneli (kapalılar dahil)."""
    return {"ok": True, "beceriler": skills_panel.panel_rows(state)}


def set_skill_visibility(state: ReplState, data: Mapping[str, Any]) -> dict[str, Any]:
    name = data.get("ad")
    if not isinstance(name, str) or not name.strip():
        return {"ok": False, "hata": "'ad' alanı dolu bir beceri adı olmalı."}
    items = {item.name: visibility for item, visibility in skills_panel.panel_items(state)}
    if name not in items:
        return {"ok": False, "hata": f"'{name}' becerisi bulunamadı (eklenti becerileri hariç)."}
    raw = data.get("gorunurluk", "dongu")
    if raw in (None, "", "dongu"):
        value = next_visibility(items[name])
    else:
        try:
            value = SkillVisibility(str(raw).strip().lower())
        except ValueError:
            return {"ok": False, "hata": f"Geçersiz görünürlük: {raw}"}
    text = skills_panel.save_changes(state, {name: value})
    ok = text.startswith("skillOverrides kaydedildi")
    return {"ok": ok, "gorunurluk": value.value, "metin": text, **({} if ok else {"hata": text})}
