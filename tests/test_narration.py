"""Claude gibi konuşma: işe başlamadan giriş paragrafı ve adımlar arasında ara anlatım.

Ölçüldü (30 Eylül, masaüstü): nemotron çırak araç çağırırken hiç metin yazmıyordu;
sohbette yalnız alt alta adım satırları görünüyordu, kullanıcı ne anlaşıldığını ve
neye geçildiğini hiç okumuyordu.
"""

from __future__ import annotations

from fusion_cli.core.events import NarrationPublished
from fusion_cli.core.tools import TodoItem, TodoStatus, ToolContext
from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps, run_agent
from fusion_cli.engines.agent.narration import todo_transitions
from fusion_cli.providers.web_browser import WebBrowserError

from .fakes import (
    AlwaysApprove,
    RecordingSink,
    ScriptedProvider,
    make_config,
    model_result,
    tool_call,
)


class _Publisher:
    def __init__(self, sink: RecordingSink) -> None:
        self.sink = sink

    def publish(self, event: object) -> None:
        self.sink.handle(event)


def _deps(tmp_path):
    sink = RecordingSink()
    deps = AgentDeps(
        config=make_config(
            agent=ModelSpec(name="cirak", model="nvidia_nim/cirak"), task_model_map={}
        ),
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )
    return deps, sink


def _patch(monkeypatch, provider):
    from fusion_cli.engines.agent import loop, narration

    monkeypatch.setattr(loop, "build_provider", lambda _spec, **_kwargs: provider)
    monkeypatch.setattr(narration, "build_provider", lambda _spec, **_kwargs: provider)


def test_yeni_adima_gecis_ara_anlatim_uretir() -> None:
    once = (
        TodoItem("Dosyayı oku", TodoStatus.COMPLETED),
        TodoItem("Testi yaz", TodoStatus.PENDING),
    )
    sonra = (
        TodoItem("Dosyayı oku", TodoStatus.COMPLETED),
        TodoItem("Testi yaz", TodoStatus.IN_PROGRESS),
    )

    assert todo_transitions(once, sonra) == ("Şimdi “Testi yaz” adımına geçiyorum.",)
    assert todo_transitions(sonra, sonra) == ()


async def test_karmasik_iste_once_giris_paragrafi_yazilir(monkeypatch, tmp_path) -> None:
    deps, sink = _deps(tmp_path)
    provider = ScriptedProvider(
        [
            model_result(
                "İsteği şöyle anladım: yeni bir modül ekleyeceğim. "
                "Önce yapıyı okuyup sonra yazacağım."
            ),
            model_result(tool_calls=(tool_call("write_file", path="a.py", content="x = 1\n"),)),
            model_result("Modül eklendi."),
        ]
    )
    _patch(monkeypatch, provider)

    await run_agent("a.py dosyasını oluştur ve içine x değişkenini yaz", deps)

    anlatim = [event.text for event in sink.events if isinstance(event, NarrationPublished)]
    assert anlatim and anlatim[0].startswith("İsteği şöyle anladım")
    # Giriş, işi yapan ilk çağrıdan önce gelir ve araçsız istenir.
    assert provider.seen_requests[0] == []


async def test_basit_sohbette_giris_paragrafi_istenmez(monkeypatch, tmp_path) -> None:
    deps, sink = _deps(tmp_path)
    provider = ScriptedProvider([model_result("Merhaba!")])
    _patch(monkeypatch, provider)

    await run_agent("Merhaba", deps)

    assert provider.calls == 1
    assert not any(isinstance(event, NarrationPublished) for event in sink.events)


async def test_giris_saglayicisi_kurulamazsa_ana_tur_surer(monkeypatch, tmp_path) -> None:
    """Yardımcı giriş çağrısı kurulamazsa dosya yazma turu yine çalışır."""
    from fusion_cli.engines.agent import narration

    deps, _sink = _deps(tmp_path)
    provider = ScriptedProvider(
        [
            model_result(tool_calls=(tool_call("write_file", path="a.py", content="x = 1\n"),)),
            model_result("Modül eklendi."),
        ]
    )
    _patch(monkeypatch, provider)

    def giris_kurulamaz(_spec, **_kwargs):
        raise WebBrowserError("test sağlayıcısı kurulamadı")

    monkeypatch.setattr(narration, "build_provider", giris_kurulamaz)
    sonuc = await run_agent("a.py dosyasını oluştur ve içine x değişkenini yaz", deps)

    assert sonuc.ok
    assert (tmp_path / "a.py").read_text() == "x = 1\n"
