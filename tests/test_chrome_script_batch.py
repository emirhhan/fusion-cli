"""#432: Chrome'da betik (javascript_tool) ve toplu eylem (browser_batch) karşılıkları."""

from __future__ import annotations

import pytest

from fusion_cli.config.permission_rules import PermissionDecision, PermissionRuleSet, parse_rule
from fusion_cli.core.tools import ToolContext, ToolEffect
from fusion_cli.engines.agent.approval import (
    ApprovalAnswer,
    ApprovalMode,
    Decision,
    build_policy,
    resolve_request,
)
from fusion_cli.tools import chrome_script
from fusion_cli.tools.builtin import build_registry

_REGISTRY = build_registry()


class _Kopru:
    def __init__(self, cevap: dict | None = None, describe: dict | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._cevap = cevap or {"ok": True, "veri": {"changed": True}}
        self._describe = describe or {"name": "Devam", "type": "button"}

    async def invoke(self, name, data):
        self.calls.append((name, data))
        if name.startswith("describe"):
            return {"ok": True, "veri": self._describe}
        if name == "javascript":
            return self._cevap
        if name == "snapshot":
            return {"ok": True, "veri": {"title": "Sayfa"}}
        return {"ok": True, "veri": {"changed": True}}


class _Prompter:
    def __init__(self) -> None:
        self.asked: list[object] = []

    async def confirm(self, request):
        self.asked.append(request)
        return ApprovalAnswer.SESSION


def _ctx(tmp_path, kopru: _Kopru) -> ToolContext:
    return ToolContext(root=tmp_path, chrome=kopru)  # type: ignore[arg-type]


def _rules(*specs: tuple[str, PermissionDecision]) -> PermissionRuleSet:
    return PermissionRuleSet(tuple(parse_rule(t, d, source="t") for t, d in specs))


async def test_betik_son_ifadenin_degerini_dondurur(tmp_path):
    kopru = _Kopru({"ok": True, "veri": {"result": '{"a":1}', "truncated": False}})
    result = await chrome_script.chrome_javascript({"text": "({a:1})"}, _ctx(tmp_path, kopru))
    assert result.ok and result.output == '{"a":1}'
    assert kopru.calls == [("javascript", {"code": "({a:1})"})]


async def test_betik_hatasi_ve_bos_betik_basarisiz(tmp_path):
    kopru = _Kopru({"ok": True, "veri": {"error": "EvalError: CSP"}})
    result = await chrome_script.chrome_javascript({"text": "1"}, _ctx(tmp_path, kopru))
    assert not result.ok and "EvalError" in result.output
    assert not (await chrome_script.chrome_javascript({"text": " "}, _ctx(tmp_path, kopru))).ok


async def test_betik_izinleri_atla_dahil_her_seferinde_sorulur(tmp_path):
    context = _ctx(tmp_path, _Kopru())
    tool = _REGISTRY.get("chrome_javascript")
    request = await resolve_request(tool, {"text": "1"}, root=tmp_path, context=context)
    assert request.effect is ToolEffect.REMOTE_DESTRUCTIVE and not request.can_remember
    prompter = _Prompter()
    policy = build_policy(ApprovalMode.BYPASS, prompter)
    assert await policy.decide(request) is Decision.ALLOW
    assert await policy.decide(request) is Decision.ALLOW
    assert len(prompter.asked) == 2


async def test_toplu_cagri_sirayla_calisir_ilk_hatada_durur(tmp_path):
    kopru = _Kopru({"ok": False, "hata": "yok"})
    actions = [
        {"name": "chrome_page", "input": {}},
        {"name": "chrome_javascript", "input": {"text": "x"}},
        {"name": "chrome_click", "input": {"ref": "e1"}},
    ]
    result = await chrome_script.chrome_batch({"actions": actions}, _ctx(tmp_path, kopru))
    assert (
        not result.ok and "[1] chrome_page" in result.output and "2. öğede durdu" in result.output
    )
    # Önce onay anındaki öğe tarifleri okunur (#432 çalışma anı denetimi), sonra sırayla çalışır.
    assert [name for name, _ in kopru.calls] == ["describe", "snapshot", "javascript"]


@pytest.mark.parametrize(
    "actions",
    [[], [{"name": "chrome_batch", "input": {}}], [{"name": "run_shell", "input": {}}],
     [{"name": "chrome_page", "input": {}}] * 21],
)  # fmt: skip
def test_gecersiz_toplu_cagri(actions):
    assert isinstance(chrome_script.batch_items({"actions": actions}), str)


async def test_toplu_cagrida_oge_deny_kurali_butun_cagriyi_kapatir(tmp_path):
    context = _ctx(tmp_path, _Kopru())
    rules = _rules(("chrome_click", PermissionDecision.DENY))
    actions = [
        {"name": "chrome_page", "input": {}},
        {"name": "chrome_click", "input": {"ref": "e"}},
    ]
    request = await resolve_request(
        _REGISTRY.get("chrome_batch"),
        {"actions": actions},
        root=tmp_path,
        context=context,
        rules=rules,
    )
    assert request.pre_denied is not None and "2. öğe (chrome_click)" in request.pre_denied


async def test_toplu_yukleme_read_kuralina_tabidir(tmp_path):
    context = _ctx(tmp_path, _Kopru())
    rules = _rules(("Read(./gizli/**)", PermissionDecision.DENY))
    actions = [
        {
            "name": "chrome_action",
            "input": {"action": "upload", "ref": "e3", "value": "gizli/a.txt"},
        }
    ]
    request = await resolve_request(
        _REGISTRY.get("chrome_batch"),
        {"actions": actions},
        root=tmp_path,
        context=context,
        rules=rules,
    )
    assert request.pre_denied is not None


async def test_toplu_cagri_en_siki_ogenin_etkisini_alir(tmp_path):
    context = _ctx(tmp_path, _Kopru())
    tool = _REGISTRY.get("chrome_batch")
    okuma = await resolve_request(
        tool, {"actions": [{"name": "chrome_page", "input": {}}]}, root=tmp_path, context=context
    )
    assert okuma.read_only
    betikli = await resolve_request(
        tool,
        {"actions": [{"name": "chrome_page", "input": {}},
                     {"name": "chrome_javascript", "input": {"text": "1"}}]},
        root=tmp_path,
        context=context,
    )  # fmt: skip
    assert betikli.effect is ToolEffect.REMOTE_DESTRUCTIVE and not betikli.read_only
    prompter = _Prompter()
    assert await build_policy(ApprovalMode.BYPASS, prompter).decide(betikli) is Decision.ALLOW
    assert len(prompter.asked) == 1


def test_yeni_araclar_yalniz_tarayici_isinde_sunulur():
    from fusion_cli.engines.agent.loop import SCOPED_TOOLS

    assert SCOPED_TOOLS["chrome_javascript"] == "masaustu"
    assert SCOPED_TOOLS["chrome_batch"] == "masaustu"


def test_eklenti_betigi_son_ifadeyi_dondurur():
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node") or "/opt/homebrew/opt/node@22/bin/node"
    if not Path(node).exists():
        pytest.skip("node kurulu değil")
    root = Path(__file__).resolve().parents[1]
    done = subprocess.run(
        [node, str(root / "tests/e2e/chrome_javascript_unit.mjs")],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "chrome-javascript ✓" in done.stdout


class _GezinenKopru(_Kopru):
    """Gezinmeden sonra aynı ref parola alanını gösterir."""

    def __init__(self) -> None:
        super().__init__(describe={"name": "Ara", "type": "text"})

    async def invoke(self, name, data):
        if name == "navigate":
            self._describe = {"name": "Parola", "type": "password"}
        return await super().invoke(name, data)


async def test_toplu_cagri_calisma_aninda_hassas_alani_yeniden_denetler(tmp_path):
    """Onay anında sıradan görünen alan önceki öğeden sonra parola alanı olduysa durur (#432)."""
    kopru = _GezinenKopru()
    context = _ctx(tmp_path, kopru)
    args = {"actions": [
        {"name": "chrome_navigate", "input": {"url": "https://example.com/login"}},
        {"name": "chrome_type", "input": {"ref": "e5", "text": "gizli"}},
    ]}  # fmt: skip
    request = await resolve_request(_REGISTRY.get("chrome_batch"), args, root=tmp_path,
                                    context=context)  # fmt: skip
    assert request.effect is not ToolEffect.REMOTE_DESTRUCTIVE
    result = await chrome_script.chrome_batch(args, context)
    assert not result.ok and "ayrı onay" in result.output
    assert "type" not in [name for name, _ in kopru.calls]
