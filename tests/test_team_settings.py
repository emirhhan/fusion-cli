"""Alt ajan tanımındaki ayarların koşuya uygulanması (P-034).

Ölçüldü (31 Ekim): `.claude/agents/<ad>.md` frontmatter'ındaki model/permissionMode/
maxTurns/skills/mcpServers/effort/disallowedTools alanları okunmuyor, alt ajan üst
ajanın kipini ve araç kümesini aynen alıyor, onay kartı "kim istiyor"u söylemiyordu.
"""

from __future__ import annotations

import dataclasses
import logging
from types import SimpleNamespace

from fusion_cli.core.reasoning import ReasoningEffort
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import team_settings
from fusion_cli.engines.agent.approval import (
    ApprovalMode,
    ApprovalRequest,
    Decision,
    build_policy,
    strictest_mode,
)
from fusion_cli.engines.agent.loop import AgentDeps
from fusion_cli.engines.agent.team import (
    GENERIC_PERSONA,
    SubTask,
    resolve_persona,
    spawn_agent_tool,
)
from fusion_cli.engines.agent.team_policy import allowed_tools
from fusion_cli.tools.capabilities import CapabilityRegistry
from tests.agent_harness import Publisher
from tests.fakes import AlwaysApprove, RecordingSink, make_config


class _Tool:
    name = "write_file"


class _KaydedenPolitika:
    def __init__(self) -> None:
        self.istekler: list[ApprovalRequest] = []

    async def decide(self, request: ApprovalRequest) -> Decision:
        self.istekler.append(request)
        return Decision.ALLOW


def _persona(**fields):
    return dataclasses.replace(GENERIC_PERSONA, **fields)


def _deps(tmp_path, *, mode=ApprovalMode.AUTO, **runtime):
    kurulan: list[ApprovalMode] = []

    def _kur(wanted: ApprovalMode):
        kurulan.append(wanted)
        return build_policy(wanted, AlwaysApprove())

    deps = AgentDeps(
        config=make_config(runtime=runtime) if runtime else make_config(),
        publisher=Publisher(RecordingSink()),
        policy=build_policy(mode, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        capabilities=CapabilityRegistry(tmp_path / "ev", tmp_path),
        approval_mode=lambda: mode,
        policy_for_mode=_kur,
    )
    return deps, kurulan


def test_izin_kipi_yalniz_sikilasir():
    assert strictest_mode(ApprovalMode.AUTO, ApprovalMode.PLAN) is ApprovalMode.PLAN
    assert strictest_mode(ApprovalMode.AUTO, ApprovalMode.BYPASS) is ApprovalMode.AUTO
    # Üst `bypass` olsa bile `auto` isteyen alt ajan bypass'ı miras almaz.
    assert strictest_mode(ApprovalMode.BYPASS, ApprovalMode.AUTO) is ApprovalMode.AUTO
    assert strictest_mode(ApprovalMode.PLAN, None) is ApprovalMode.PLAN


def test_alt_ajan_politikasi_ust_kipi_sikilastirir_gevsetmez(tmp_path):
    deps, kurulan = _deps(tmp_path)

    team_settings.child_policies(deps, _persona(permission_mode="plan"), "x")
    assert kurulan == [ApprovalMode.PLAN]

    team_settings.child_policies(deps, _persona(permission_mode="bypass"), "x")
    assert kurulan[-1] is ApprovalMode.AUTO

    # Tanınmayan kip yok sayılır: üstün politikası etiketlenerek aynen kullanılır.
    policy, factory = team_settings.child_policies(deps, _persona(permission_mode="uydurma"), "x")
    assert isinstance(policy, team_settings.LabeledPolicy) and len(kurulan) == 2
    assert factory is None  # üstte `policy_factory` yoktu


def test_torun_ajanin_kipi_ust_ajanin_sikilastirilmis_kipine_gore_hesaplanir(tmp_path):
    """Ölçüldü (31 Ekim): çocuğa `approval_mode` oturumun lambda'sı (auto) aktarılıyordu;
    `permissionMode: plan` ajan A'nın çocuğu B (`acceptEdits`) strictest(auto, acceptEdits)
    = acceptEdits ile dosya yazabiliyordu. Torun, A'nın sıkılaştırılmış kipini temel alır."""
    deps, kurulan = _deps(tmp_path)

    cocuk_kipi = team_settings.child_approval_mode(deps, _persona(permission_mode="plan"))
    assert cocuk_kipi is not None and cocuk_kipi() is ApprovalMode.PLAN
    # Kip istemeyen çocuk üstün kipini olduğu gibi devralır.
    duz = team_settings.child_approval_mode(deps, _persona())
    assert duz is not None and duz() is ApprovalMode.AUTO

    deps.approval_mode = cocuk_kipi
    team_settings.child_policies(deps, _persona(permission_mode="acceptEdits"), "torun")
    assert kurulan[-1] is ApprovalMode.PLAN


def test_bellek_araclari_yasagi_ve_salt_okur_sozlesmesini_asmaz(tmp_path):
    """Ölçüldü (31 Ekim): `remember`/`memory_read` disallowedTools'a ve salt-okur göreve
    bakılmadan ekleniyordu; 'dosya değiştirme' denen görevde remember .fusion/ altına yazardı."""

    class _BosDefter:
        def is_remote(self, name: str) -> bool:
            return "__" in name

        def __iter__(self):
            return iter(())

    deps = SimpleNamespace(base_registry=_BosDefter(), tool_context=ToolContext(root=tmp_path))
    mevcut = ("read_file", "remember", "memory_read")

    yasakli = _persona(memory_scope="project", disallowed_tools=frozenset({"remember"}))
    assert allowed_tools(deps, yasakli, SubTask("iş"), available=mevcut) == {
        "read_file",
        "memory_read",
    }
    bellekli = _persona(memory_scope="project", tools=frozenset({"read_file"}))
    assert allowed_tools(deps, bellekli, SubTask("iş"), available=mevcut) == {
        "read_file",
        "remember",
        "memory_read",
    }
    salt = allowed_tools(deps, bellekli, SubTask("iş", read_only=True), available=mevcut)
    assert salt is not None and "memory_read" in salt and "remember" not in salt


def test_yapilandirilmamis_mcp_sunucusu_uyarilir(tmp_path, caplog):
    """`mcpServers` Claude Code'da ajana özel sunucu TANIMLAR; Fusion'da yalnız süzgeçtir.
    Mevcut uzak araçlarda olmayan sunucu adı sessiz kalmasın."""
    deps = SimpleNamespace(
        base_registry=SimpleNamespace(is_remote=lambda name: "__" in name),
        tool_context=ToolContext(root=tmp_path),
    )
    mevcut = ("read_file", "github__search")

    with caplog.at_level(logging.WARNING):
        sonuc = allowed_tools(
            deps, _persona(mcp_servers=("github", "playwright")), SubTask("iş"), available=mevcut
        )

    assert sonuc == {"read_file", "github__search"}
    assert any(
        "playwright" in str(record.__dict__.get("sunucular", "")) for record in caplog.records
    )


async def test_etiketli_politika_istege_ajan_kimligi_basar():
    inner = _KaydedenPolitika()
    policy = team_settings.LabeledPolicy(inner, "Geliştirici (kodcu-1)")

    await policy.decide(ApprovalRequest(tool=_Tool(), args={"path": "a"}, danger=None))
    await policy.decide(ApprovalRequest(tool=_Tool(), args={}, danger=None, agent_label="İç (x-2)"))

    assert inner.istekler[0].agent_label == "Geliştirici (kodcu-1)"
    # Daha içteki ajanın etiketi ezilmez.
    assert inner.istekler[1].agent_label == "İç (x-2)"


def test_model_alani_saglayici_model_bicimini_ister():
    parent = make_config().agent

    spec = team_settings.child_model(_persona(name="denetci", model="openrouter/a/b"), parent)
    assert spec is not None and spec.model == "openrouter/a/b" and spec.name == "ajan:denetci"
    assert spec.fallback == parent.models

    assert team_settings.child_model(_persona(model="sonnet"), parent) is None
    assert team_settings.child_model(_persona(model="inherit"), parent) is None
    assert team_settings.child_model(_persona(model="gpt-5"), parent) is None


def test_efor_alani_yalniz_alt_ajanin_yapilandirmasini_degistirir():
    config = make_config()

    child = team_settings.child_config(config, _persona(effort="high"))
    assert child.runtime.reasoning_effort is ReasoningEffort.HIGH
    assert config.runtime.reasoning_effort is not ReasoningEffort.HIGH or config is not child

    assert team_settings.child_config(config, _persona(effort="cok")) is config
    assert team_settings.child_config(config, _persona()) is config


def test_yasak_araclar_ve_mcp_suzgeci_kumeyi_yalniz_daraltir(tmp_path):
    deps = SimpleNamespace(
        base_registry=SimpleNamespace(is_remote=lambda name: "__" in name),
        tool_context=ToolContext(root=tmp_path),
    )
    mevcut = ("read_file", "run_shell", "github__search", "jira__list")
    gorev = SubTask("iş")

    tam = _persona(disallowed_tools=frozenset({"run_shell"}))
    assert allowed_tools(deps, tam, gorev, available=mevcut) == {
        "read_file",
        "github__search",
        "jira__list",
    }

    mcp = _persona(mcp_servers=("github",))
    assert allowed_tools(deps, mcp, gorev, available=mevcut) == {
        "read_file",
        "run_shell",
        "github__search",
    }

    desen = _persona(tools=frozenset({"read_file", "jira__*"}))
    assert allowed_tools(deps, desen, gorev, available=mevcut) == {"read_file", "jira__list"}

    # Kısıtsız kişilik, kısıt alanı yoksa None (tam set) kalır.
    assert allowed_tools(deps, GENERIC_PERSONA, gorev, available=mevcut) is None


def test_yasak_mcp_sunucu_deseni_gercek_adlara_acilir(tmp_path):
    """Ölçüldü (31 Ekim): `disallowedTools: mcp__srv` → `srv__*` deseni açılmadan küme
    farkına sokuluyordu; `srv__a`, `srv__b` açık kalıyordu (deny bypass)."""
    deps = SimpleNamespace(
        base_registry=SimpleNamespace(is_remote=lambda name: "__" in name),
        tool_context=ToolContext(root=tmp_path),
    )
    mevcut = ("read_file", "srv__a", "srv__b", "jira__list")

    yasak = _persona(disallowed_tools=frozenset({"srv__*"}))
    assert allowed_tools(deps, yasak, SubTask("iş"), available=mevcut) == {
        "read_file",
        "jira__list",
    }
    dar = _persona(tools=frozenset({"read_file", "srv__*"}), disallowed_tools=frozenset({"srv__*"}))
    assert allowed_tools(deps, dar, SubTask("iş"), available=mevcut) == {"read_file"}


def test_on_yuklenen_beceriler_brife_girer_bulunmayan_atlanir(tmp_path):
    beceri = tmp_path / "ev" / ".claude" / "skills" / "kod-inceleme"
    beceri.mkdir(parents=True)
    (beceri / "SKILL.md").write_text(
        "---\nname: kod-inceleme\ndescription: inceler\n---\nÖnce testleri oku.", encoding="utf-8"
    )
    deps, _ = _deps(tmp_path)

    metin = team_settings.preloaded_skills(deps, _persona(skills=("kod-inceleme", "yok")))

    assert "# Ön yüklenen beceri: kod-inceleme" in metin and "Önce testleri oku." in metin
    assert "yok" not in metin.split("kod-inceleme", 1)[1]
    assert team_settings.preloaded_skills(deps, GENERIC_PERSONA) == ""


async def test_alt_ajan_tanimi_kosuya_uygulanir(tmp_path):
    """Uçtan uca: tanımdaki model, kip, tur tavanı ve efor alt ajanın deps'ine iner."""
    ajanlar = tmp_path / ".claude" / "agents"
    ajanlar.mkdir(parents=True)
    (ajanlar / "denetci.md").write_text(
        "---\nname: denetci\ndescription: denetler\ntools: Read\nmodel: openrouter/a/b\n"
        "permissionMode: plan\nmaxTurns: 3\neffort: high\n---\nSen denetçisin.",
        encoding="utf-8",
    )
    deps, kurulan = _deps(tmp_path, agent_max_steps=64)
    gorulen: dict[str, object] = {}

    async def _sahte_ajan(task, sub_deps, **kwargs):
        gorulen["model"] = sub_deps.active_model_override
        gorulen["step_limit"] = kwargs["step_limit"]
        gorulen["effort"] = sub_deps.config.runtime.reasoning_effort
        gorulen["allowed"] = kwargs["allowed_tools"]
        gorulen["extra"] = kwargs["extra_system"]
        istek = ApprovalRequest(tool=_Tool(), args={"path": "a"}, danger=None)
        gorulen["karar"] = await sub_deps.policy.decide(istek)
        return SimpleNamespace(final_text="bitti", ok=True, tool_calls_made=0)

    arac = spawn_agent_tool(deps, depth=0, run_agent=_sahte_ajan)
    sonuc = await arac.run({"task": "incele", "uzman": "denetci"}, deps.tool_context)

    assert "bitti" in sonuc.output
    assert getattr(gorulen["model"], "model", None) == "openrouter/a/b"
    assert gorulen["step_limit"] == 3
    assert gorulen["effort"] is ReasoningEffort.HIGH
    assert gorulen["allowed"] == {"read_file", "view_file"}
    assert "Sen denetçisin." in gorulen["extra"]
    # `plan` kipi `auto` üstten SIKI: alt ajanın politikası plan kipiyle kuruldu ve
    # düzenleme isteği reddedildi.
    assert kurulan and kurulan[0] is ApprovalMode.PLAN
    assert gorulen["karar"] is not Decision.ALLOW


def test_tanimdaki_bilinmeyen_arac_adi_uyarilir_ama_ajan_cozulur(tmp_path, caplog):
    ajanlar = tmp_path / ".claude" / "agents"
    ajanlar.mkdir(parents=True)
    (ajanlar / "x.md").write_text(
        "---\nname: x\ndescription: d\ntools: Read, Uydurma\n---\ngövde", encoding="utf-8"
    )

    with caplog.at_level("WARNING"):
        persona = resolve_persona(CapabilityRegistry(tmp_path / "ev", tmp_path), "x")

    assert persona.unknown_tools == ("Uydurma",)
    assert persona.tools is not None and "read_file" in persona.tools
    assert any("tanınmayan araç" in kayit.message for kayit in caplog.records)


async def test_bellek_alanli_alt_ajan_kendi_bellegini_ve_araclarini_alir(tmp_path):
    """P-055: `memory: project` olan ajan kendi BELLEK.md'sini ve remember aracını alır."""
    ajanlar = tmp_path / ".claude" / "agents"
    ajanlar.mkdir(parents=True)
    (ajanlar / "kodcu.md").write_text(
        "---\nname: kodcu\ndescription: d\ntools: Read\nmemory: project\n---\ngövde",
        encoding="utf-8",
    )
    (ajanlar / "duz.md").write_text(
        "---\nname: duz\ndescription: d\ntools: Read\n---\ngövde", encoding="utf-8"
    )
    deps, _ = _deps(tmp_path)
    gorulen: dict[str, object] = {}

    async def _sahte_ajan(task, sub_deps, **kwargs):
        gorulen[task] = (sub_deps.plain_memory, kwargs["allowed_tools"])
        if sub_deps.plain_memory is not None:
            sub_deps.plain_memory.remember("testler", "önce testleri çalıştır")
        return SimpleNamespace(final_text="ok", ok=True, tool_calls_made=0)

    arac = spawn_agent_tool(deps, depth=0, run_agent=_sahte_ajan)
    await arac.run({"task": "a", "uzman": "kodcu", "salt_okunur": True}, deps.tool_context)
    await arac.run({"task": "b", "uzman": "duz"}, deps.tool_context)

    bellek, araclar = gorulen["a"]
    assert bellek is not None and bellek.directory == tmp_path / ".fusion" / "ajan-bellek" / "kodcu"
    # Salt-okur görevde yalnız okuma aracı açılır; `remember` yazma sözleşmesini aşmaz.
    assert "memory_read" in set(araclar or ()) and "remember" not in set(araclar or ())
    assert (
        "önce testleri" in (tmp_path / ".fusion/ajan-bellek/kodcu/konular/testler.md").read_text()
    )
    # Bellek alanı olmayan üye ne bellek ne aracı alır.
    assert gorulen["b"][0] is None and "remember" not in (gorulen["b"][1] or ())
