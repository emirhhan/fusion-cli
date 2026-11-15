"""Playbook'un kip/onay kapısı ve başarısızlık bildirimi (A3-27)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import ClassVar

import pytest

from fusion_cli.core.events import StatusChanged
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import playbook_stage
from fusion_cli.engines.agent.approval import ApprovalMemory, ApprovalMode, build_policy
from fusion_cli.engines.playbook import Playbook, PlaybookStep
from fusion_cli.tools import build_registry


class _Publisher:
    def __init__(self) -> None:
        self.events: list[object] = []

    def publish(self, event: object) -> None:
        self.events.append(event)


class _Soran:
    """Onay isteyen kipin kullanıcıya sorusunu kaydeder ve reddeder."""

    def __init__(self) -> None:
        self.sorular: list[str] = []

    async def confirm(self, request):
        self.sorular.append(str(request.args.get("command")))
        return False


class _Kosucu:
    calisan: ClassVar[list[str]] = []
    kod = 0

    def __init__(self, **_: object) -> None:
        pass

    async def run(self, command: str) -> int:
        type(self).calisan.append(command)
        return type(self).kod


_KITAP = Playbook(
    id="ornek",
    description="örnek",
    triggers=("format",),
    steps=(
        PlaybookStep("Çalıştır: ruff check .", "ruff check .", rollback="git restore src/a.py"),
    ),
    checks=("ruff check .",),
)


def _deps(tmp_path, mod: ApprovalMode, soran: _Soran) -> SimpleNamespace:
    return SimpleNamespace(
        config=SimpleNamespace(runtime=SimpleNamespace(playbooks=True)),
        tool_context=ToolContext(root=tmp_path),
        base_registry=build_registry(),
        policy=build_policy(mod, soran, ApprovalMemory()),
        policy_factory=None,
        allowed_commands=frozenset(),
        publisher=_Publisher(),
    )


@pytest.fixture(autouse=True)
def _sahte_kosucu(monkeypatch):
    _Kosucu.calisan = []
    _Kosucu.kod = 0
    monkeypatch.setattr(playbook_stage, "ShellStepRunner", _Kosucu)
    monkeypatch.setattr(playbook_stage, "build_playbooks", lambda root: (_KITAP,))


async def test_manuel_kipte_onaylanmayan_playbook_hic_baslamaz(tmp_path):
    soran = _Soran()
    deps = _deps(tmp_path, ApprovalMode.SECURITY, soran)

    sonuc = await playbook_stage.maybe_run_playbook("kodu format et", deps)

    assert sonuc is None
    assert _Kosucu.calisan == []
    assert soran.sorular
    mesajlar = [e.message for e in deps.publisher.events if isinstance(e, StatusChanged)]
    assert any("atlandı" in m for m in mesajlar)


async def test_plan_kipinde_playbook_degisiklik_yapmaz(tmp_path):
    deps = _deps(tmp_path, ApprovalMode.PLAN, _Soran())

    assert await playbook_stage.maybe_run_playbook("kodu format et", deps) is None
    assert _Kosucu.calisan == []


async def test_bypass_kipinde_playbook_calisir(tmp_path):
    deps = _deps(tmp_path, ApprovalMode.BYPASS, _Soran())

    sonuc = await playbook_stage.maybe_run_playbook("kodu format et", deps)

    assert sonuc is not None
    assert "ruff check ." in _Kosucu.calisan


async def test_basarisiz_playbook_kullaniciya_bildirilir(tmp_path):
    _Kosucu.kod = 1
    deps = _deps(tmp_path, ApprovalMode.BYPASS, _Soran())

    sonuc = await playbook_stage.maybe_run_playbook("kodu format et", deps)

    assert sonuc is None
    mesajlar = [e.message for e in deps.publisher.events if isinstance(e, StatusChanged)]
    assert any("başarısız" in m and "geri alındı" in m for m in mesajlar)
