"""Kişilik süzgeçli ders geri çağırma (P-055).

Ölçüldü (31 Ekim): alt ajan turundan çıkan dersler kişilik bilgisi taşımıyordu; `memory:`
alanlı (kendi belleği olan) ajanın öğrendiği ders ana ajana ve diğer ajanlara da dönüyordu,
ajan kendi derslerini ayırt edemiyordu.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fusion_cli.core.memory import Lesson, LessonKind, agent_lesson_tag, visible_to
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.learning_steps import lesson_tags
from fusion_cli.engines.agent.loop import AgentDeps
from fusion_cli.memory import lessons
from fusion_cli.memory.lessons import _to_metadata

from .fakes import AlwaysApprove, make_config


class _Publisher:
    def publish(self, event: object) -> None:
        del event


class _Koleksiyon:
    """Sorguya her dersi aynı uzaklıkla döndüren sahte Chroma koleksiyonu."""

    def __init__(self, items: list[Lesson]) -> None:
        self._items = items

    def count(self) -> int:
        return len(self._items)

    def query(self, *, query_texts: list[str], n_results: int) -> dict[str, Any]:
        del query_texts
        chosen = self._items[:n_results]
        return {
            "documents": [[item.text for item in chosen]],
            "metadatas": [[_to_metadata(item, 0.0) for item in chosen]],
            "distances": [[0.1 for _ in chosen]],
        }


def _deps(tmp_path: Path, owner: str = "") -> AgentDeps:
    return AgentDeps(
        config=make_config(),
        publisher=_Publisher(),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        lesson_owner=owner,
    )


def test_ders_sahibi_ajan_etiketi_derse_yazilir(tmp_path: Path):
    assert lesson_tags(_deps(tmp_path, owner="inceleyici")) == ("ajan:inceleyici",)
    assert lesson_tags(_deps(tmp_path)) == ()


def test_ajan_etiketli_ders_yalniz_sahibine_gorunur():
    sahip = (agent_lesson_tag("inceleyici"),)

    assert visible_to(sahip, sahip)
    assert not visible_to(sahip, ())
    assert not visible_to(sahip, (agent_lesson_tag("yazar"),))
    assert visible_to(("python",), ())


def test_recall_kisilik_suzgeci_ve_proje_siniri(tmp_path: Path, monkeypatch):
    proje = str(tmp_path / "proje")
    items = [
        Lesson(text="genel ders", kind=LessonKind.SUCCESS),
        Lesson(
            text="inceleyici dersi",
            kind=LessonKind.SUCCESS,
            tags=(agent_lesson_tag("inceleyici"),),
            workspace=proje,
        ),
        Lesson(text="yazar dersi", kind=LessonKind.SUCCESS, tags=(agent_lesson_tag("yazar"),)),
    ]
    monkeypatch.setattr(lessons, "get_collection", lambda *a, **k: _Koleksiyon(items))
    memory = lessons.ChromaLessonMemory(tmp_path)

    def texts(**kwargs: Any) -> set[str]:
        return {item.text for item in memory.recall("ders", limit=6, **kwargs)}

    inceleyici = (agent_lesson_tag("inceleyici"),)
    assert texts() == {"genel ders"}
    assert texts(tags=inceleyici, workspace=proje) == {"genel ders", "inceleyici dersi"}
    # Ajan etiketi teknoloji katmanı sayılmaz: projeye özel ajan dersi başka projeye taşınmaz.
    assert texts(tags=inceleyici, workspace=str(tmp_path / "baska")) == {"genel ders"}


async def test_bellekli_alt_ajan_ders_sahibi_olur_belleksiz_olmaz(tmp_path: Path, monkeypatch):
    from types import SimpleNamespace

    from fusion_cli.engines.agent import team
    from fusion_cli.engines.agent.team import GENERIC_PERSONA, SubTask
    from fusion_cli.tools.capabilities import CapabilityRegistry

    ajanlar = tmp_path / "ev" / ".claude" / "agents"
    ajanlar.mkdir(parents=True)
    (ajanlar / "bellekli.md").write_text(
        "---\nname: bellekli\ndescription: d\nmemory: project\n---\nGövde", encoding="utf-8"
    )
    deps = _deps(tmp_path)
    deps.capabilities = CapabilityRegistry(tmp_path / "ev", tmp_path)
    sahipler: list[str] = []

    async def _sahte_ajan(task: str, sub_deps: AgentDeps, **kwargs: object) -> object:
        sahipler.append(sub_deps.lesson_owner)
        return SimpleNamespace(final_text="tamam", ok=True, tool_calls_made=0, messages=[])

    for ad in ("bellekli", GENERIC_PERSONA.name):
        await team.run_subagent(deps, SubTask("iş", persona=ad), depth=0, run_agent=_sahte_ajan)

    assert sahipler == ["bellekli", ""]
