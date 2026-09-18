"""Derslerin teknoloji etiketi — aynı tür projede yeniden kullanılabilmesi için."""

from __future__ import annotations

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.learning_steps import lesson_tags
from fusion_cli.engines.agent.loop import AgentDeps

from .fakes import AlwaysApprove, make_config


class _Publisher:
    def publish(self, event):
        del event


def _deps(tmp_path, tools=()):
    return AgentDeps(
        config=make_config(),
        publisher=_Publisher(),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path, available_tools=set(tools)),
    )


def test_proje_turu_etiket_olur(tmp_path):
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")

    assert lesson_tags(_deps(tmp_path)) == ("godot",)


def test_bagli_mcp_sunucusu_etiket_olur(tmp_path):
    """MCP dersi projeye değil SUNUCUYA aittir: godot MCP'nin kuralı, godot MCP
    bağlı olan her projede geçerlidir."""
    deps = _deps(tmp_path, tools=("godot__add_node", "godot__save_scene", "read_file"))

    assert lesson_tags(deps) == ("mcp:godot",)


def test_proje_ve_mcp_etiketleri_birlikte_donulur(tmp_path):
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    deps = _deps(tmp_path, tools=("godot__add_node",))

    assert lesson_tags(deps) == ("godot", "mcp:godot")


def test_taninmayan_dizin_etiketsizdir(tmp_path):
    assert lesson_tags(_deps(tmp_path)) == ()


# --------------------------------------------------------------------------- #
# Hatırlama bütçesi — kaldırıldı (B5): dersler artık tur başında kendiliğinden
# enjekte edilmiyor, `recall_lessons` aracıyla modelin isteğiyle geliyor; bkz.
# `test_single_loop_routing.py::test_dersler_kendiliginden_hatirlanmaz_ama_aracla_istenebilir`.
# --------------------------------------------------------------------------- #
# Hazır derslerin güveni
# --------------------------------------------------------------------------- #


def test_olculmus_dersler_tam_guvenle_baslar():
    from fusion_cli.core.memory import DEFAULT_LESSON_CONFIDENCE
    from fusion_cli.memory.seed import MEASURED_LESSONS, SEED_LESSONS

    olculmus = {ders.text for ders in MEASURED_LESSONS}
    for ders in SEED_LESSONS:
        if ders.text in olculmus:
            assert ders.confidence == DEFAULT_LESSON_CONFIDENCE


def test_yazilan_dersler_dusuk_guvenle_baslar():
    """Ölçülmeden yazılan ders, ölçülmüş dersle AYNI ağırlıkta girmemeli.

    Yanlışsa `reinforce` onu aşağı iter ve eşiğin altına düşünce artık enjekte
    edilmez; doğruysa gerçek kullanım yukarı çeker. Böylece görmeden yazmak
    güvenli hâle gelir.
    """
    from fusion_cli.core.memory import DEFAULT_LESSON_CONFIDENCE
    from fusion_cli.memory.seed import UNMEASURED_CONFIDENCE, WRITTEN_LESSONS

    assert UNMEASURED_CONFIDENCE < DEFAULT_LESSON_CONFIDENCE
    for ders in WRITTEN_LESSONS:
        assert ders.confidence == UNMEASURED_CONFIDENCE
