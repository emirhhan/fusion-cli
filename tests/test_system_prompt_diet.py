from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYSTEM_PROMPT = ROOT / "src/fusion_cli/engines/agent/prompts/system.md"


def prompt() -> str:
    return SYSTEM_PROMPT.read_text(encoding="utf-8")


def test_system_prompt_context_butcesini_asmaz():
    text = prompt()

    assert len(text) <= 5_000


def test_system_prompt_kritik_calisma_ilkelerini_korur():
    text = prompt()

    required = (
        "Kanıta dayan",
        "`dosya:satır`",
        "belirsiz gereksinim",
        "Okumak değişiklik isteyen görevde teslim değildir",
        "test, lint, build",
        "İşlevsel görevlerde",
        "commit oluşturma",
        "Yıkıcı",
        "API anahtarı",
        "yapılmış gibi sunma",
    )

    for phrase in required:
        assert phrase in text


def test_tool_protokolleri_system_promptta_tekrar_edilmez():
    text = prompt()

    procedural_tool_names = (
        "replace_range",
        "edit_file",
        "multi_edit",
        "todo_write",
        "spawn_agent",
        "council",
        "find_skill",
        "read_skill",
        "run_shell",
        "web_fetch",
        "browser_open",
        "browser_read",
        "browser_type",
        "browser_click",
        "browser_screenshot",
    )

    for name in procedural_tool_names:
        assert name not in text


def test_system_prompt_kimlik_sinirlarini_korur():
    text = prompt()

    assert text.startswith("<kimlik>\n")
    assert text.endswith("</kimlik>\n")
