"""MCP araç adı Claude Code biçiminde: `mcp__<sunucu>__<araç>` (#242).

Claude Code (code.claude.com/docs/en/mcp, "Tool naming"): geçersiz karakterler `_`
olur, tam adı 128 karakteri aşan araç modele gönderilmez. Fusion çok sağlayıcılı:
65-128 arası ad OpenAI/Gemini sınırı (64) için özetle kısaltılır.
"""

from __future__ import annotations

import logging
import re
from types import SimpleNamespace

from fusion_cli.core.mcp_tool_names import (
    canonical_mcp_name,
    legacy_mcp_name,
    mcp_server_of,
    split_mcp_tool_name,
)
from fusion_cli.mcp_bridge.client import McpClient
from fusion_cli.mcp_bridge.tool_name import MAX_TOOL_NAME_CHARS, fusion_tool_name
from fusion_cli.tools import ToolRegistry

_RULE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def test_kayit_adi_mcp_onekli():
    assert fusion_tool_name("fusion", "list_dir") == "mcp__fusion__list_dir"


def test_eklenti_sunucusu_adi_plugin_onekiyle():
    assert fusion_tool_name("plugin_gh_api", "get") == "mcp__plugin_gh_api__get"


def test_gecersiz_karakterler_alt_cizgi_olur_ozet_eklenmez():
    assert fusion_tool_name("META ADS", "get.campaigns v2") == "mcp__META_ADS__get_campaigns_v2"


def test_uzun_ad_saglayici_sinirini_asmaz_ve_ayirt_edilir():
    one = fusion_tool_name("s" * 40, "a" * 60)
    two = fusion_tool_name("s" * 40, "a" * 59 + "b")

    assert one is not None and two is not None
    assert len(one) <= MAX_TOOL_NAME_CHARS and _RULE.match(one)
    assert one != two


def test_128_karakteri_asan_arac_disarida_kalir():
    assert fusion_tool_name("s" * 60, "a" * 70) is None


def test_ad_ayristirma_yeni_ve_eski_yazim():
    assert split_mcp_tool_name("mcp__github__get_issue") == ("github", "get_issue")
    assert split_mcp_tool_name("github__get_issue") == ("github", "get_issue")
    assert split_mcp_tool_name("read_file") is None
    assert mcp_server_of("mcp__plugin_x_y__z") == "plugin_x_y"
    assert canonical_mcp_name("github__x") == "mcp__github__x"
    assert canonical_mcp_name("read_file") == "read_file"
    assert legacy_mcp_name("mcp__github__x") == "github__x"


class _Arac:
    def __init__(self, name: str) -> None:
        self.name = name
        self.description = ""
        self.inputSchema: dict[str, object] = {}
        self.annotations = None


class _Oturum:
    def __init__(self, *names: str) -> None:
        self._names = names

    async def list_tools(self, cursor=None):
        return SimpleNamespace(tools=[_Arac(name) for name in self._names], nextCursor=None)


async def test_register_into_kuralsiz_adi_kayit_defterine_temiz_yazar():
    client = McpClient(())
    client._sessions["META ADS"] = _Oturum("get campaigns")
    registry = ToolRegistry()

    eklenen = await client.register_into(registry)

    assert eklenen == ("mcp__META_ADS__get_campaigns",)
    assert registry.get(eklenen[0]) is not None


async def test_register_into_128_asan_araci_atlar_ve_gunluge_yazar(caplog):
    client = McpClient(())
    client._sessions["srv"] = _Oturum("kisa", "a" * 130)
    registry = ToolRegistry()

    with caplog.at_level(logging.WARNING):
        eklenen = await client.register_into(registry)

    assert eklenen == ("mcp__srv__kisa",)
    assert any("128" in record.getMessage() for record in caplog.records)


def test_izin_kurali_yeni_ve_eski_mcp_yazimini_eslestirir():
    from fusion_cli.config.permission_rules import PermissionDecision, PermissionRule
    from fusion_cli.tools.permission_match import _tool_matches, claude_tool_names

    def kural(arac: str) -> PermissionRule:
        return PermissionRule(tool=arac, specifier=None, decision=PermissionDecision.ALLOW)

    hedef = "mcp__github__get_issue"
    assert _tool_matches(kural("mcp__github"), hedef)
    assert _tool_matches(kural("mcp__github__*"), hedef)
    assert _tool_matches(kural("mcp__github__get_issue"), hedef)
    assert _tool_matches(kural("github__get_issue"), hedef)  # eski Fusion yazımı
    assert not _tool_matches(kural("mcp__gitlab"), hedef)
    assert claude_tool_names(hedef)[:2] == (hedef, "github__get_issue")


def test_headless_allowed_tools_mcp_adi_aynen_kalir():
    from fusion_cli.cli.headless import map_claude_tool_names

    sonuc = map_claude_tool_names(frozenset({"mcp__github__get_issue", "jira__list"}))

    assert sonuc == frozenset({"mcp__github__get_issue", "mcp__jira__list"})


# --- 65-128 karakterlik ad: kısaltılmış kayıt adı Claude'un tam adıyla eşleşir (#242) ---

_LONG_SERVER = "my_server"
_LONG_TOOL = "get_extremely_long_customer_account_balance_history_report"
_LONG_FULL = f"mcp__{_LONG_SERVER}__{_LONG_TOOL}"


def _long_registered() -> str:
    short = fusion_tool_name(_LONG_SERVER, _LONG_TOOL)
    assert short is not None and short != _LONG_FULL and len(short) <= MAX_TOOL_NAME_CHARS
    return short


def test_uzun_adda_tam_adla_yazilan_deny_kurali_kisaltilmis_kayit_adina_uyar():
    from fusion_cli.config.permission_rules import (
        PermissionDecision,
        PermissionRuleSet,
        parse_rule,
    )
    from fusion_cli.tools.permission_match import evaluate

    short = _long_registered()
    rule = parse_rule(_LONG_FULL, PermissionDecision.DENY)
    assert rule is not None
    rules = PermissionRuleSet((rule,))

    match = evaluate(rules, short, {}, None)

    assert match is not None and match.decision is PermissionDecision.DENY


def test_uzun_adda_onek_joker_kurali_da_kisaltilmis_ada_uyar():
    from fusion_cli.config.permission_rules import (
        PermissionDecision,
        PermissionRuleSet,
        parse_rule,
    )
    from fusion_cli.tools.permission_match import evaluate

    short = _long_registered()
    pattern = f"mcp__{_LONG_SERVER}__get_extremely_long_customer_account_balance_*"
    rule = parse_rule(pattern, PermissionDecision.DENY)
    assert rule is not None

    match = evaluate(PermissionRuleSet((rule,)), short, {}, None)

    assert match is not None and match.decision is PermissionDecision.DENY


def test_uzun_adda_kanca_eslestiricisi_tam_adi_tanir():
    from fusion_cli.tools.permission_match import claude_tool_names

    short = _long_registered()

    assert _LONG_FULL in claude_tool_names(short)
    assert canonical_mcp_name(short) == _LONG_FULL


def test_uzun_adda_allowed_tools_tam_adi_kayit_adina_acilir():
    from fusion_cli.tools.capabilities import expand_tool_patterns

    short = _long_registered()

    assert short in expand_tool_patterns({_LONG_FULL}, (short, "read_file"))
