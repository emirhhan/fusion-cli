"""Düzenleme sonrası kancalar: kullanıcının komutu değişen dosya için çalışır."""

from __future__ import annotations

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.edit_hooks import run_post_edit_hooks
from fusion_cli.engines.agent.loop import AgentDeps, run_agent
from tests.agent_harness import Publisher, install_provider
from tests.fakes import (
    AlwaysApprove,
    RecordingSink,
    ScriptedProvider,
    make_config,
    model_result,
    tool_call,
)


async def test_basarili_kanca_sessiz_kalir_yol_guvenle_yerlesir(tmp_path):
    hedef = tmp_path / "adı boşluklu.txt"
    hedef.write_text("x", encoding="utf-8")

    sonuc = await run_post_edit_hooks(("test -f {path}",), hedef, tmp_path)

    assert sonuc is None


async def test_basarisiz_kanca_ciktisi_modele_doner(tmp_path):
    sonuc = await run_post_edit_hooks(("echo bicim-hatasi; exit 3",), tmp_path / "a", tmp_path)

    assert sonuc is not None and "çıkış kodu 3" in sonuc and "bicim-hatasi" in sonuc


async def test_dongu_dosya_yazinca_kancayi_calistirir(tmp_path, monkeypatch):
    saglayici = install_provider(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("write_file", path="a.txt", content="selam")]),
                model_result("bitti"),
            ]
        ),
    )
    deps = AgentDeps(
        config=make_config(
            runtime={"post_edit_commands": ("echo kanca:{path} > kanca.log; exit 1",)}
        ),
        publisher=Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )

    await run_agent("yaz", deps)

    assert "a.txt" in (tmp_path / "kanca.log").read_text(encoding="utf-8")
    arac_mesaji = next(m for m in saglayici.seen_messages[1] if m.role == "tool")
    assert "DÜZENLEME KANCASI BAŞARISIZ" in arac_mesaji.content
