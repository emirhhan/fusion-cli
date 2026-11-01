"""`/copy [N]` blok seçicisi (#231)."""

from __future__ import annotations

from pathlib import Path

from fusion_cli.appserver.commands import command_choices
from fusion_cli.cli.repl import copy_blocks
from fusion_cli.cli.repl.export_commands import copy_answer
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.loader import load_config
from fusion_cli.core.types import Message
from fusion_cli.memory.factory import null_memory
from fusion_cli.ui.clipboard import ClipboardResult

CEVAP = "Şöyle:\n```python\nprint(1)\n```\n> alıntı bir\n> alıntı iki\nson"


def _state(tmp_path: Path, answer: str = CEVAP) -> ReplState:
    source = tmp_path / "config.yaml"
    source.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    state = ReplState(
        config=load_config(source), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )
    state.history = [Message("user", "soru"), Message("assistant", answer)]
    return state


def test_bloklar_ayrisir():
    assert copy_blocks.answer_blocks(CEVAP) == [
        ("kod:python", "print(1)"),
        ("alıntı", "alıntı bir\nalıntı iki"),
    ]
    assert copy_blocks.copy_choices("düz metin") == ()


def test_blok_varsa_secici_acilir_secilen_blok_kopyalanir(tmp_path: Path):
    state = _state(tmp_path)
    kopyalanan: list[str] = []

    def copier(text: str) -> ClipboardResult:
        kopyalanan.append(text)
        return ClipboardResult(ok=True)

    sorulan = []

    def picker(choices, *, title, alt_keys=()):
        sorulan.append([c.value for c in choices])
        return "1"

    assert "8 karakter" in copy_answer(state, "", copier=copier, picker=picker)
    assert sorulan == [["tam", "1", "2"]] and kopyalanan == ["print(1)"]
    copy_answer(state, "1 tam", copier=copier, picker=picker)
    assert kopyalanan[-1] == CEVAP and len(sorulan) == 1
    assert "seçim" in copy_answer(state, "", copier=copier, picker=lambda c, **_: None)


def test_blok_yoksa_dogrudan_tam_yanit(tmp_path: Path):
    state = _state(tmp_path, "yalın cevap")
    kopyalanan: list[str] = []

    def copier(text: str) -> ClipboardResult:
        kopyalanan.append(text)
        return ClipboardResult(ok=True)

    copy_answer(state, "", copier=copier, picker=lambda c, **_: "x")
    assert kopyalanan == ["yalın cevap"]


def test_masaustu_blok_secicisi(tmp_path: Path):
    payload = command_choices(_state(tmp_path), "copy", "")
    assert payload is not None and payload["devam"]["komut"] == "copy"
    assert {row["deger"] for row in payload["secenekler"]} == {"tam", "1", "2"}
    assert command_choices(_state(tmp_path), "copy", "1 2") is None


def test_w_secimi_panoya_degil_dosyaya_yazar(tmp_path: Path):
    """Claude Code: seçicide `w` seçimi panoya değil dosyaya yazar (SSH üzerinde)."""
    state = _state(tmp_path)
    kopyalanan: list[str] = []

    def copier(text: str) -> ClipboardResult:
        kopyalanan.append(text)
        return ClipboardResult(ok=True)

    def picker(choices, *, title, alt_keys=()):
        assert "w" in alt_keys
        return "w:1"

    sonuc = copy_answer(state, "", copier=copier, picker=picker, now=lambda: 0.0)
    yazilan = list(tmp_path.glob("fusion-copy-*.py"))
    assert kopyalanan == [] and len(yazilan) == 1
    assert yazilan[0].read_text(encoding="utf-8") == "print(1)\n"
    assert str(yazilan[0]) in sonuc
    # TUI modalı seçimi argümana `N w:K` olarak ekler; tam yanıt .md olur.
    copy_answer(state, "1 w:tam", copier=copier, picker=picker, now=lambda: 1.0)
    assert len(list(tmp_path.glob("fusion-copy-*.md"))) == 1 and kopyalanan == []
