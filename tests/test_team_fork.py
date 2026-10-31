"""Fork alt ajan: ana bağlamı devralan izole alt görev (P-054).

Ölçüldü (31 Ekim): SubTask yalnız görev metni + kişilik taşıyordu; alt ajan ana geçmişi
görmüyor, `/subtask` yoktu, beceri `context: fork` okunmuyordu.
"""

from __future__ import annotations

from types import SimpleNamespace

from fusion_cli.core.types import Message, ToolCall
from fusion_cli.engines.agent import history as history_rules
from fusion_cli.engines.agent import team_fork
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps
from fusion_cli.engines.agent.team import SubTask, _parse_subtask, run_subagent, spawn_agent_tool
from fusion_cli.tools.capabilities import CapabilityRegistry
from tests.agent_harness import Publisher
from tests.fakes import AlwaysApprove, RecordingSink, make_config


def _deps(tmp_path):
    return AgentDeps(
        config=make_config(),
        publisher=Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContextFactory(tmp_path),
        capabilities=CapabilityRegistry(tmp_path / "ev", tmp_path),
    )


def ToolContextFactory(tmp_path):  # noqa: N802 - kısa yardımcı
    from fusion_cli.core.tools import ToolContext

    return ToolContext(root=tmp_path)


def test_fork_gecmisi_sistemi_dusurur_ve_eski_arac_ciktisini_temizler():
    uzun = "x" * 40_000
    gecmis = [
        Message("system", "SİSTEM"),
        Message("user", "kök görev"),
        Message("assistant", "", tool_calls=(ToolCall(id="1", name="read_file", arguments="{}"),)),
        Message("tool", uzun, tool_call_id="1"),
        Message("assistant", "okudum"),
        Message("user", "devam"),
        Message("assistant", "", tool_calls=(ToolCall(id="2", name="read_file", arguments="{}"),)),
        Message("tool", uzun, tool_call_id="2"),
        Message("assistant", "bitti"),
    ]

    fork = team_fork.fork_history(gecmis)

    assert fork[0].role == "user" and fork[0].content == "kök görev"
    assert all(message.role != "system" for message in fork)
    assert history_rules.total_chars(fork) <= team_fork.FORK_MAX_CHARS
    # En eski araç çıktısı nota indi; en SON araç çıktısı korunur.
    assert len(fork[2].content) < 200 and fork[6].content == uzun
    assert team_fork.fork_history(None) == [] and team_fork.fork_history([]) == []


def test_fork_gecmisi_hala_uzunsa_kok_ve_sonu_korur_arayi_notlar():
    gecmis = [Message("system", "S"), Message("user", "kök")]
    for index in range(60):
        gecmis.append(Message("user", f"soru {index} " + "y" * 2_000))
        gecmis.append(Message("assistant", f"cevap {index} " + "z" * 2_000))

    fork = team_fork.fork_history(gecmis)

    assert fork[0].content == "kök"
    assert any("çıkarıldı" in message.content for message in fork)
    assert fork[-1].content.startswith("cevap 59")
    assert len(fork) <= team_fork.FORK_KEEP_RECENT + 3


def test_baglam_miras_alani_kapali_guvenli_okunur():
    assert _parse_subtask({"task": "a", "baglam_miras": True}).inherit_context is True  # type: ignore[union-attr]
    assert _parse_subtask({"task": "a", "baglam_miras": "evet"}).inherit_context is True  # type: ignore[union-attr]
    assert _parse_subtask({"task": "a"}).inherit_context is False  # type: ignore[union-attr]
    assert _parse_subtask({"task": "a", "baglam_miras": "belki"}).inherit_context is False  # type: ignore[union-attr]


async def test_fork_alt_ajan_ana_gecmisi_devralir_temiz_alt_ajan_almaz(tmp_path):
    deps = _deps(tmp_path)
    canli = [Message("system", "S"), Message("user", "ana görev"), Message("assistant", "tamam")]
    deps.live_history = lambda: canli
    gorulen: dict[str, object] = {}

    async def _sahte_ajan(task, sub_deps, **kwargs):
        gorulen[task] = (kwargs.get("history"), kwargs["extra_system"])
        return SimpleNamespace(final_text="ok", ok=True, tool_calls_made=0)

    arac = spawn_agent_tool(deps, depth=0, run_agent=_sahte_ajan)
    await arac.run({"task": "fork", "baglam_miras": True}, deps.tool_context)
    await arac.run({"task": "temiz"}, deps.tool_context)

    fork_gecmis, fork_not = gorulen["fork"]
    assert [m.content for m in fork_gecmis] == ["ana görev", "tamam"]
    assert team_fork.FORK_BRIEF in fork_not
    assert gorulen["temiz"][0] is None and team_fork.FORK_BRIEF not in gorulen["temiz"][1]


async def test_run_forked_turn_ana_gecmise_yalniz_ozeti_ekler(tmp_path, monkeypatch):
    deps = _deps(tmp_path)
    gecmis = [Message("system", "S"), Message("user", "önceki"), Message("assistant", "cevap")]

    gorulen: dict[str, object] = {}

    async def _sahte_ajan(task, sub_deps, **kwargs):
        assert [m.content for m in kwargs["history"]] == ["önceki", "cevap"]
        gorulen.update(kwargs)
        return SimpleNamespace(final_text="alt görev özeti", ok=True, tool_calls_made=3)

    monkeypatch.setattr("fusion_cli.engines.agent.loop.run_agent", _sahte_ajan)
    sonuc = await team_fork.run_forked_turn(
        "testleri çalıştır",
        deps,
        history=gecmis,
        extra_system="# Oturum kişiliği: Keşif\nyalnız oku",
        allowed_tools={"read_file", "write_file"},
        images=("data:image/png;base64,AAAA",),
        step_limit=5,
    )

    assert sonuc.final_text == "alt görev özeti" and sonuc.ok and sonuc.tool_calls_made == 3
    # Ölçüldü (31 Ekim): `**_ignored` oturum kişiliğini, `context: fork` becerisinin metnini,
    # araç kısıtını ve görselleri atıyordu; salt-okur kişilik fork içinde yazabiliyordu.
    assert "yalnız oku" in str(gorulen["extra_system"])
    assert team_fork.FORK_BRIEF in str(gorulen["extra_system"])
    assert gorulen["allowed_tools"] == {"read_file", "write_file"}
    assert gorulen["images"] == ("data:image/png;base64,AAAA",)
    assert gorulen["step_limit"] == 5
    assert [m.content for m in sonuc.messages] == [
        "S",
        "önceki",
        "cevap",
        "testleri çalıştır",
        "alt görev özeti",
    ]
    assert sonuc.messages[-1].role == "assistant"


async def test_live_history_yoksa_fork_temiz_baglamla_kosar(tmp_path):
    deps = _deps(tmp_path)
    gorulen: dict[str, object] = {}

    async def _sahte_ajan(task, sub_deps, **kwargs):
        gorulen["history"] = kwargs.get("history")
        return SimpleNamespace(final_text="ok", ok=True, tool_calls_made=0)

    await run_subagent(deps, SubTask("a", inherit_context=True), depth=0, run_agent=_sahte_ajan)

    assert gorulen["history"] == []


def test_fork_gecmisi_sondaki_cevapsiz_arac_cagrisini_dusurur():
    """Ölçüldü (31 Ekim): `spawn_agent baglam_miras=true` çalışırken canlı geçmişin son
    mesajı cevapsız `assistant(tool_calls=spawn_agent)` idi; alt ajan bunun arkasına user
    eklediğinde sağlayıcı 'orphan tool call' (400) veriyordu."""
    gecmis = [
        Message("system", "S"),
        Message("user", "kök görev"),
        Message("assistant", "", tool_calls=(ToolCall(id="1", name="read_file", arguments="{}"),)),
        Message("tool", "içerik", tool_call_id="1"),
        Message(
            "assistant", "", tool_calls=(ToolCall(id="2", name="spawn_agent", arguments="{}"),)
        ),
    ]

    fork = team_fork.fork_history(gecmis)

    assert fork[-1].role == "tool" and fork[-1].tool_call_id == "1"
    assert not any(call.name == "spawn_agent" for m in fork for call in m.tool_calls)


def test_fork_gecmisi_kismi_cevapli_paralel_cagriyi_da_dusurur():
    gecmis = [
        Message("user", "kök"),
        Message(
            "assistant",
            "",
            tool_calls=(
                ToolCall(id="a", name="read_file", arguments="{}"),
                ToolCall(id="b", name="spawn_agent", arguments="{}"),
            ),
        ),
        Message("tool", "ok", tool_call_id="a"),
    ]

    fork = team_fork.fork_history(gecmis)

    assert [m.role for m in fork] == ["user"]


def test_fork_kirpmasi_basi_kopuk_arac_sonucuyla_baslamaz():
    """60 KB üstü kırpmada `recent` dilimi bir `tool` mesajıyla başlayabiliyordu (çağrısı
    atılmış orphan sonuç); kesim tur sınırına kaydırılır."""
    gecmis = [Message("system", "S"), Message("user", "kök")]
    for index in range(40):
        gecmis.append(Message("user", f"soru {index}"))
        gecmis.append(
            Message(
                "assistant",
                "",
                tool_calls=(ToolCall(id=f"c{index}", name="read_file", arguments="{}"),),
            )
        )
        gecmis.append(Message("tool", "s" * 1_500, tool_call_id=f"c{index}"))
        gecmis.append(Message("tool", "t" * 1_500, tool_call_id=f"c{index}"))
        gecmis.append(Message("assistant", "cevap " + "z" * 1_500))

    fork = team_fork.fork_history(gecmis)

    assert history_rules.total_chars(fork) <= team_fork.FORK_MAX_CHARS
    cevaplanan = {m.tool_call_id for m in fork if m.role == "tool"}
    cagrilan = {call.id for m in fork for call in m.tool_calls}
    assert cevaplanan == cagrilan
    assert fork[-1].content.startswith("cevap")
    for index, message in enumerate(fork):
        if message.role == "tool":
            assert fork[index - 1].role == "tool" or fork[index - 1].tool_calls


async def test_fork_arac_tavani_kisiligin_kumesini_yalniz_daraltir(tmp_path, monkeypatch):
    """Üstten gelen tavan (`allowed_tools`) üyenin kendi kümesiyle KESİŞİR; genişletmez."""
    ajanlar = tmp_path / ".claude" / "agents"
    ajanlar.mkdir(parents=True)
    (ajanlar / "dar.md").write_text(
        "---\nname: dar\ndescription: d\ntools: Read, Write\n---\ngövde", encoding="utf-8"
    )
    deps = _deps(tmp_path)
    gorulen: dict[str, object] = {}

    async def _sahte_ajan(task, sub_deps, **kwargs):
        gorulen["allowed_tools"] = kwargs["allowed_tools"]
        return SimpleNamespace(final_text="ok", ok=True, tool_calls_made=0)

    await run_subagent(
        deps,
        SubTask("a", persona="dar", tool_cap=frozenset({"read_file", "run_shell"})),
        depth=0,
        run_agent=_sahte_ajan,
    )

    assert gorulen["allowed_tools"] == {"read_file"}
