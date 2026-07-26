"""Faz 4 — çalıştırılabilir beceri (playbook) kütüphanesi.

Ön-koşul eşleşmesi ve çalıştırma/geri-alma sahte bir StepRunner ile yan etkisiz
test edilir. Kütüphanedeki gerçek playbook'ların yapısı da doğrulanır.
"""

from __future__ import annotations

from fusion_cli.engines.playbook import Playbook, PlaybookStep, run_playbook
from fusion_cli.engines.playbook.library import build_playbooks
from fusion_cli.engines.playbook.matching import find_match, matches


class _FakeRunner:
    """Komut → çıkış kodu eşlemesiyle önceden belirlenmiş sahte koşucu."""

    def __init__(self, codes: dict[str, int] | None = None, *, default: int = 0) -> None:
        self._codes = codes or {}
        self._default = default
        self.ran: list[str] = []

    async def run(self, command: str) -> int:
        self.ran.append(command)
        return self._codes.get(command, self._default)


def _playbook(**overrides: object) -> Playbook:
    base = {
        "id": "ornek",
        "description": "örnek akış",
        "triggers": ("format",),
        "steps": (
            PlaybookStep("adım bir", "cmd1", rollback="undo1"),
            PlaybookStep("adım iki", "cmd2", rollback="undo2"),
        ),
        "checks": ("check1",),
    }
    base.update(overrides)
    return Playbook(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Eşleşme
# --------------------------------------------------------------------------- #


def test_tetikleyici_gecince_eslesir():
    playbook = _playbook(triggers=("format", "lint"))
    assert matches(playbook, "kodu format et") is True


def test_tetikleyici_gecmezse_eslesmez():
    playbook = _playbook(triggers=("format",))
    assert matches(playbook, "yeni özellik ekle") is False


def test_cok_sozcuklu_tetikleyici_alt_dize_ile_eslesir():
    playbook = _playbook(triggers=("testleri çalıştır",))
    assert matches(playbook, "lütfen testleri çalıştır") is True


def test_find_match_ilk_esleseni_secer():
    a = _playbook(id="a", triggers=("format",))
    b = _playbook(id="b", triggers=("format",))
    assert find_match((a, b), "format et").id == "a"


def test_find_match_yoksa_none():
    assert find_match((_playbook(triggers=("format",)),), "alakasız") is None


# --------------------------------------------------------------------------- #
# Çalıştırma ve geri alma
# --------------------------------------------------------------------------- #


async def test_basarili_akis_adimlari_sirayla_kosturur():
    runner = _FakeRunner()
    result = await run_playbook(_playbook(), runner)
    assert result.ok is True
    assert runner.ran == ["cmd1", "cmd2", "check1"]
    assert result.rolled_back is False


async def test_adim_basarisiz_olunca_geri_alinir():
    runner = _FakeRunner({"cmd2": 1})
    result = await run_playbook(_playbook(), runner)
    assert result.ok is False
    # cmd1, cmd2 çalıştı; cmd2 kırıldı → ters sırada undo2, undo1 çalışır (check yok).
    assert runner.ran == ["cmd1", "cmd2", "undo2", "undo1"]
    assert result.rolled_back is True


async def test_dogrulama_kirilinca_geri_alinir():
    runner = _FakeRunner({"check1": 1})
    result = await run_playbook(_playbook(), runner)
    assert result.ok is False
    assert runner.ran == ["cmd1", "cmd2", "check1", "undo2", "undo1"]
    assert result.rolled_back is True


async def test_geri_alma_komutu_olmayan_adim_atlanir():
    steps = (PlaybookStep("adım", "cmd1"),)  # rollback yok
    runner = _FakeRunner({"check1": 1})
    result = await run_playbook(_playbook(steps=steps), runner)
    assert result.ok is False
    assert result.rolled_back is False
    assert runner.ran == ["cmd1", "check1"]


async def test_checks_bossa_adimlarin_bitmesi_basari():
    runner = _FakeRunner()
    result = await run_playbook(_playbook(checks=()), runner)
    assert result.ok is True
    assert runner.ran == ["cmd1", "cmd2"]


# --------------------------------------------------------------------------- #
# Gerçek kütüphane
# --------------------------------------------------------------------------- #


def test_kutuphane_playbooklari_tutarli(tmp_path):
    """Kütüphane artık PROJEDEN üretilir; sabit liste yok."""
    (tmp_path / "pyproject.toml").write_text(
        "[dependency-groups]\ndev=['pytest','ruff']\n", encoding="utf-8"
    )
    playbooks = build_playbooks(tmp_path)

    assert len(playbooks) >= 2
    ids = [playbook.id for playbook in playbooks]
    assert len(ids) == len(set(ids))  # kimlikler benzersiz
    for playbook in playbooks:
        assert playbook.triggers
        assert playbook.steps
