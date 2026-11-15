"""Çağrılan becerinin sonraki turlarda kalması ve sıkıştırma sonrası yeniden eklenmesi (#140).

Claude Code (skills, "Skill content lifecycle"): işlenmiş SKILL.md konuşmada kalır; sıkıştırmadan
SONRA her becerinin son çağrısı beceri başına 5.000, toplam 25.000 token ile yeniden eklenir.
Modelin `Skill` aracıyla yüklediği beceri de aynı kurala girer.
"""

from __future__ import annotations

from fusion_cli.core.types import Message, ToolCall
from fusion_cli.engines.agent.history import CLEARED_TOOL_OUTPUT, CONVERSATION_SUMMARY_PREFIX
from fusion_cli.engines.agent.skill_context import (
    CHARS_PER_TOKEN,
    PER_SKILL_TOKENS,
    TRUNCATED_NOTE,
    InvokedSkills,
)

GOVDE = "M" * 40_000


def _skill_turu(call_id: str = "c1", content: str = GOVDE) -> list[Message]:
    return [
        Message("user", "raporu hazırla"),
        Message("assistant", "", tool_calls=(ToolCall(call_id, "Skill", '{"skill": "rapor"}'),)),
        Message("tool", content, tool_call_id=call_id, name="Skill", ok=True),
    ]


def test_skill_araci_sonucu_gecmisteyken_tasinmaz() -> None:
    kayit = InvokedSkills("s").observe(_skill_turu())

    assert kayit.carried_block() == ""
    assert [entry.name for entry in kayit.entries] == ["rapor"]


def test_skill_araci_sonucu_ozetlenince_5k_ile_yeniden_eklenir() -> None:
    kayit = InvokedSkills("s").observe(_skill_turu())
    ozet = [Message("user", f"{CONVERSATION_SUMMARY_PREFIX}\nönceki iş", harness_note=True)]

    kayit = kayit.observe(ozet)
    blok = kayit.carried_block()

    assert blok.count("M") == PER_SKILL_TOKENS * CHARS_PER_TOKEN
    assert TRUNCATED_NOTE in blok


def test_esik_temizligi_dusurdugu_skill_sonucu_yeniden_eklenir() -> None:
    kayit = InvokedSkills("s").observe(_skill_turu())
    temiz = _skill_turu(content=CLEARED_TOOL_OUTPUT.format(chars=len(GOVDE)))

    assert "MMMM" in kayit.observe(temiz).carried_block()


def test_kullanici_ad_govdesi_ilk_turlarda_tam_ozetten_sonra_kirpilir() -> None:
    kayit = InvokedSkills("s").remember("uzun", "U" * 40_000)
    gecmis = [Message("user", "devam"), Message("assistant", "tamam")]

    once = kayit.observe(gecmis).carried_block()
    assert once.count("U") == 40_000 and TRUNCATED_NOTE not in once

    ozet = [Message("user", f"{CONVERSATION_SUMMARY_PREFIX}\nözet", harness_note=True)]
    sonra = kayit.observe(gecmis).observe(ozet).carried_block()
    assert sonra.count("U") == PER_SKILL_TOKENS * CHARS_PER_TOKEN


def test_ayni_skill_sonucu_ikinci_kez_kaydedilmez() -> None:
    gecmis = _skill_turu()
    kayit = InvokedSkills("s").observe(gecmis).remember("rapor", "kullanıcı yeniden çağırdı")

    kayit = kayit.observe(gecmis)

    assert [entry.body for entry in kayit.entries] == ["kullanıcı yeniden çağırdı"]


def test_repl_durumu_skill_aracini_gecmisten_kaydeder(tmp_path) -> None:
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.memory.factory import null_memory

    from .fakes import make_config

    state = ReplState(config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path)
    state.history = _skill_turu()

    assert state.take_pending_extras().context == ""
    assert [entry.name for entry in state.invoked_skills.entries] == ["rapor"]

    state.history = [Message("user", f"{CONVERSATION_SUMMARY_PREFIX}\nözet", harness_note=True)]
    assert "MMMM" in state.take_pending_extras().context
