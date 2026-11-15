"""#431: Claude in Chrome araç adları ve şemaları; eski `chrome_*` gizli takma ad."""

from __future__ import annotations

import json

from fusion_cli.appserver.chrome_feed import panel_item
from fusion_cli.config.permission_rules import PermissionDecision, PermissionRuleSet, parse_rule
from fusion_cli.core.tools import ToolContext, ToolEffect, ToolResult
from fusion_cli.core.types import ToolCall
from fusion_cli.engines.agent.approval import resolve_request
from fusion_cli.engines.agent.claude_chrome_call import claude_chrome_call
from fusion_cli.tools.builtin import build_registry
from fusion_cli.tools.claude_chrome_translate import translate

_REGISTRY = build_registry()
P = "claude-in-chrome__"


class _Kopru:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def invoke(self, name, data):
        self.calls.append((name, data))
        if name.startswith("describe"):
            return {"ok": True, "veri": {"name": "Gönder", "type": "button"}}
        return {"ok": True, "veri": {"changed": True}}


def _ctx(tmp_path, kopru=None) -> ToolContext:
    return ToolContext(root=tmp_path, chrome=kopru)  # type: ignore[arg-type]


def _call(name: str, args: dict) -> ToolCall:
    return ToolCall(id="c1", name=P + name, arguments=json.dumps(args))


def test_modele_claude_adlari_sunulur_eski_adlar_gizlidir():
    sunulan = {schema["function"]["name"] for schema in _REGISTRY.schemas()}  # type: ignore[index]
    for short in ("navigate", "read_page", "find", "form_input", "computer", "get_page_text"):
        assert P + short in sunulan
    assert P + "browser_batch" in sunulan and P + "javascript_tool" in sunulan
    assert not {name for name in sunulan if name.startswith("chrome_")}
    # Eski ad çağrılırsa çalışır (gizli takma ad).
    assert _REGISTRY.get("chrome_action") is not None


def test_ceviri_claude_argumanlarini_ic_cagriya_esler():
    assert translate(P + "navigate", {"url": "back", "tabId": 3}) == (
        "chrome_action",
        {"action": "back"},
    )
    assert translate(P + "navigate", {"url": "x.com", "tabId": 3}) == (
        "chrome_navigate",
        {"url": "x.com", "tabId": 3},
    )
    assert translate(P + "computer", {"action": "left_click", "ref": "e4"}) == (
        "chrome_click",
        {"ref": "e4"},
    )
    assert translate(P + "computer", {"action": "left_click", "coordinate": [10, 20]}) == (
        "chrome_action",
        {"action": "click_at", "value": "10,20"},
    )
    assert translate(P + "computer", {"action": "scroll", "scroll_direction": "down"}) == (
        "chrome_action",
        {"action": "scroll", "value": "down:300"},
    )
    assert translate(P + "form_input", {"ref": "e2", "value": True}) == (
        "chrome_action",
        {"action": "check", "ref": "e2", "value": "true"},
    )
    assert translate(P + "form_input", {"ref": "e2", "value": "ali"}) == (
        "chrome_type",
        {"ref": "e2", "text": "ali"},
    )
    assert translate(P + "read_console_messages", {"onlyErrors": True, "pattern": "Tip"}) == (
        "chrome_action",
        {"action": "console", "value": "errors:Tip"},
    )
    assert translate(P + "tabs_create_mcp", {}) == ("chrome_action", {"action": "new_tab"})
    assert translate(P + "computer", {"action": "wait", "duration": 1}) is None
    assert isinstance(translate(P + "computer", {"action": "left_click"}), str)


def test_coklu_tus_ve_toplu_cagri_sekme_secimiyle_cevrilir():
    keys = translate(P + "computer", {"action": "key", "text": "Tab Tab", "repeat": 2})
    assert keys is not None and keys[0] == "chrome_batch"
    assert len(keys[1]["actions"]) == 4  # type: ignore[index, arg-type]
    batch = translate(
        P + "browser_batch",
        {
            "actions": [
                {"name": "computer", "input": {"action": "screenshot", "tabId": 7}},
                {"name": "find", "input": {"query": "ara", "tabId": 7}},
                {"name": "chrome_page", "input": {}},
            ]
        },
    )
    assert batch == (
        "chrome_batch",
        {
            "actions": [
                {"name": "chrome_action", "input": {"action": "tab", "value": "7"}},
                {"name": "chrome_action", "input": {"action": "screenshot"}},
                {"name": "chrome_page", "input": {"query": "ara"}},
                {"name": "chrome_page", "input": {}},
            ]
        },
    )


async def test_dongu_cevirisi_sekmeyi_secer_ve_claude_kuralini_ic_ada_kopyalar(tmp_path):
    kopru = _Kopru()
    rules = PermissionRuleSet(
        (parse_rule("mcp__claude-in-chrome__computer", PermissionDecision.DENY, source="t"),)
    )
    sonuc = await claude_chrome_call(
        _call("computer", {"action": "left_click", "ref": "e9", "tabId": 5}),
        {"action": "left_click", "ref": "e9", "tabId": 5},
        rules,
        _ctx(tmp_path, kopru),
    )
    assert isinstance(sonuc, tuple)
    call, args, mapped = sonuc
    assert call.name == "chrome_click" and args == {"ref": "e9"}
    assert kopru.calls == [("tab_select", {"id": 5})]
    assert mapped is not None
    assert any(
        r.tool == "chrome_click" and r.decision is PermissionDecision.DENY for r in mapped.rules
    )


async def test_dongu_cevirisi_hatali_argumani_onaysiz_dondurur(tmp_path):
    sonuc = await claude_chrome_call(
        _call("computer", {"action": "zoom"}), {"action": "zoom"}, None, _ctx(tmp_path)
    )
    assert isinstance(sonuc, ToolResult) and not sonuc.ok


async def test_cevrilen_cagri_ic_aracin_yasak_eylem_onayindan_gecer(tmp_path):
    kopru = _Kopru()
    sonuc = await claude_chrome_call(
        _call("computer", {"action": "left_click", "ref": "e1"}),
        {"action": "left_click", "ref": "e1"},
        None,
        _ctx(tmp_path, kopru),
    )
    assert isinstance(sonuc, tuple)
    call, args, _rules = sonuc
    tool = _REGISTRY.get(call.name)
    assert tool is not None
    request = await resolve_request(tool, args, (), root=tmp_path, context=_ctx(tmp_path, kopru))
    # "Gönder" riskli tıklamadır: iç aracın etkisi uygulanır.
    assert request.effect in {ToolEffect.REMOTE_WRITE, ToolEffect.REMOTE_DESTRUCTIVE}


async def test_kayit_defterinden_dogrudan_cagri_ayni_ceviriyle_calisir(tmp_path):
    kopru = _Kopru()
    result = await _REGISTRY.execute(
        P + "navigate", {"url": "https://93.184.216.34", "tabId": 4}, _ctx(tmp_path, kopru)
    )
    assert result.ok
    assert kopru.calls == [("navigate", {"url": "https://93.184.216.34", "tabId": 4})]


async def test_tarayici_listesi_tek_yerel_kopruyu_gosterir(tmp_path):
    bagli = await _REGISTRY.execute(P + "list_connected_browsers", {}, _ctx(tmp_path, _Kopru()))
    assert json.loads(bagli.output)[0]["deviceId"] == "fusion-local"
    bos = await _REGISTRY.execute(P + "list_connected_browsers", {}, _ctx(tmp_path))
    assert json.loads(bos.output) == []
    secim = await _REGISTRY.execute(
        P + "select_browser", {"deviceId": "baska"}, _ctx(tmp_path, _Kopru())
    )
    assert not secim.ok
    assert not (await _REGISTRY.execute(P + "switch_browser", {}, _ctx(tmp_path))).ok


def test_panel_akisi_claude_adini_ic_adla_gosterir():
    satir = json.dumps(
        {
            "tip": "olay",
            "veri": {
                "olay": "ToolExecuted",
                "name": P + "navigate",
                "args": {"url": "https://ornek.com", "tabId": 2},
                "outcome": "ok",
                "output": "{}",
            },
        }
    )
    item = panel_item(satir)
    assert item is not None and item["arac"] == "chrome_navigate"
