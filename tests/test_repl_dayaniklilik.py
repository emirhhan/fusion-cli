"""REPL dayanıklılığı: iptalde geçmiş, işaret kaçışı, TUI/satır-içi eşitliği, canlı ayar birleşimi.

Plan bulguları: L2-05, L2-06, L2-07, L2-08, L2-12, L2-13, L2-15.
"""

from __future__ import annotations

import asyncio
import io
import re
import threading
from dataclasses import replace

import pytest
from rich.console import Console

from fusion_cli.cli.repl import loop
from fusion_cli.cli.repl.state import Engine, Reminder, ReplState, rebase_session_changes
from fusion_cli.cli.repl.tui_loop import _preview, _TuiSession
from fusion_cli.config.loader import load_config
from fusion_cli.config.writer import write_mcp_servers
from fusion_cli.core.types import Message, ModelSpec
from fusion_cli.engines.agent.approval import ApprovalMode, ApprovalRequest
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


def _state(tmp_path, **kwargs) -> ReplState:
    return ReplState(
        config=kwargs.pop("config", None) or make_config(),
        memory=null_memory(),
        root=tmp_path,
        home=tmp_path,
        **kwargs,
    )


class _Tool:
    name = "run_shell"


# --- L2-05: Rich işaret kaçışı --------------------------------------------------------


def test_onay_onizlemesi_argumandaki_isaretleri_yutmaz_ve_cokertmez():
    """Argümandaki `[/x]` MarkupError verirdi, `[bold]` sessizce yutulurdu."""
    istek = ApprovalRequest(
        tool=_Tool(),
        args={"command": "echo [/x] [bold]merhaba[/bold]"},
        danger="siler [/y]",
    )
    cikti = io.StringIO()

    Console(file=cikti, force_terminal=False, width=200).print(_preview(istek))

    metin = cikti.getvalue()
    assert "echo [/x] [bold]merhaba[/bold]" in metin
    assert "siler [/y]" in metin


async def test_komut_sonucundaki_etiketler_yutulmaz(tmp_path, monkeypatch):
    """`/model` gibi komut çıktısındaki `[strict]` etiketi Rich işareti sanılıp silinirdi."""
    from fusion_cli.config import model_select

    monkeypatch.setattr(model_select, "format_models", lambda config: "agent : x/y [strict]")
    session = _TuiSession(_state(tmp_path))

    await session._command("/model")

    duz = re.sub(r"\x1b\[[0-9;]*m", "", session.tui.transcript)
    assert "[strict]" in duz


# --- L2-12: iptalde geçmiş ve /undo ----------------------------------------------------


async def test_tui_iptalde_arac_sonuclari_gecmise_ve_degisiklikler_undo_a_girer(
    tmp_path, monkeypatch
):
    state = _state(tmp_path)
    session = _TuiSession(state)
    kayit: dict[str, object] = {}

    async def sahte(task, config, **kwargs):
        context = kwargs["tool_context"]
        kayit["context"] = context
        kwargs["journal"].save(
            [
                Message("user", task),
                Message("assistant", "dosyayı yazdım"),
            ]
        )
        raise asyncio.CancelledError

    monkeypatch.setattr("fusion_cli.cli.repl.tui_loop.run_agent_task", sahte)

    with pytest.raises(asyncio.CancelledError):
        await session._turn("a.txt yaz")

    icerikler = [message.content for message in state.history]
    assert "dosyayı yazdım" in icerikler
    assert state.last_changes is kayit["context"].changes


async def test_tui_hatada_ilk_cagri_kaydi_yoksa_kullanici_istegi_gecmise_girer(
    tmp_path, monkeypatch
):
    state = _state(tmp_path)
    state.history = [Message("user", "önceki"), Message("assistant", "cevap")]
    session = _TuiSession(state)

    async def sahte(task, config, **kwargs):
        raise RuntimeError("sağlayıcı koptu")

    monkeypatch.setattr("fusion_cli.cli.repl.tui_loop.run_agent_task", sahte)

    with pytest.raises(RuntimeError):
        await session._turn("yeni istek")

    icerikler = [message.content for message in state.history]
    assert icerikler[:3] == ["önceki", "cevap", "yeni istek"]


async def test_satir_ici_yol_iptalde_gecmisi_korur(tmp_path, monkeypatch):
    from fusion_cli.core.concurrency import BackgroundTasks

    state = _state(tmp_path)

    async def sahte_run_agent(task, deps, **kwargs):
        deps.journal.save([Message("user", task), Message("assistant", "yarım iş")])
        raise asyncio.CancelledError

    monkeypatch.setattr("fusion_cli.engines.agent.run_agent", sahte_run_agent)

    with pytest.raises(asyncio.CancelledError):
        await loop._agent_turn("görev", state, Console(quiet=True), BackgroundTasks())

    assert "yarım iş" in [message.content for message in state.history]
    assert state.last_changes is not None


# --- L2-06: TUI yolu satır-içi yolla aynı turu kurar ------------------------------------


async def test_tui_turu_saglik_ve_yetenek_kaydini_oturumdan_gecirir(tmp_path, monkeypatch):
    from fusion_cli.engines.agent import AgentOutcome

    state = _state(tmp_path)
    session = _TuiSession(state)
    cagrilar: list[dict[str, object]] = []

    async def sahte(task, config, **kwargs):
        cagrilar.append(kwargs)
        return AgentOutcome("bitti", [], 0, ok=True)

    monkeypatch.setattr("fusion_cli.cli.repl.tui_loop.run_agent_task", sahte)

    await session._turn("görev")

    assert cagrilar[0]["health"] is state.health
    assert cagrilar[0]["capabilities"] is state.capabilities


async def test_tui_turu_auto_profili_uygular(tmp_path, monkeypatch):
    from fusion_cli.engines.agent import AgentOutcome

    state = _state(tmp_path)
    state.auto_profile = True
    session = _TuiSession(state)
    secilen: list[str] = []

    async def sahte(task, config, **kwargs):
        return AgentOutcome("bitti", [], 0, ok=True)

    monkeypatch.setattr("fusion_cli.cli.repl.tui_loop.run_agent_task", sahte)
    monkeypatch.setattr(
        "fusion_cli.cli.repl.tui_loop.apply_auto_profile",
        lambda line, durum, konsol: secilen.append(line),
    )

    await session._turn("büyük bir mimari değişiklik")

    assert secilen == ["büyük bir mimari değişiklik"]


async def test_tui_hatirlatma_suresi_dolunca_gosterilir(tmp_path):
    state = _state(tmp_path)
    state.reminders.append(Reminder(due_in_seconds=0, text="süt al"))
    session = _TuiSession(state)

    session._arm_reminders()
    await session.background.drain()

    assert "süt al" in session.tui.transcript
    assert state.reminders == []


async def test_tui_her_satirdan_once_panel_degisikligini_alir(tmp_path, monkeypatch):
    state = _state(tmp_path)
    session = _TuiSession(state)
    cagrildi: list[bool] = []

    def yenile() -> bool:
        cagrildi.append(True)
        return True

    monkeypatch.setattr(ReplState, "refresh_config", lambda self: yenile())

    session._refresh_config()

    assert cagrildi == [True]
    assert "Kontrol paneli ayarları yüklendi" in session.tui.transcript


# --- L2-07 / L2-15: açılış ------------------------------------------------------------


async def test_repl_kayitli_motor_ve_onay_modunu_alir(tmp_path, monkeypatch):
    config = make_config()
    config = replace(config, runtime=replace(config.runtime, engine="fusion", approval_mode="plan"))
    alinan: list[ReplState] = []

    async def tui(state, console):
        alinan.append(state)
        return 0

    monkeypatch.delenv("FUSION_INLINE", raising=False)
    monkeypatch.setattr(loop, "is_interactive_terminal", lambda: True)
    monkeypatch.setattr("fusion_cli.cli.repl.tui_loop.run_tui_repl", tui)

    await loop.run_repl(config, memory=null_memory(), root=tmp_path, console=Console(quiet=True))

    assert alinan[0].engine is Engine.FUSION
    assert alinan[0].approval is ApprovalMode.PLAN


async def test_terminal_degilse_tam_ekran_uygulamasi_kurulmaz(tmp_path, monkeypatch):
    async def tui(state, console):
        raise AssertionError("borulu kullanımda TUI kurulmamalı")

    async def satir_yok(reader, state):
        return None

    monkeypatch.delenv("FUSION_INLINE", raising=False)
    monkeypatch.setattr(loop, "is_interactive_terminal", lambda: False)
    monkeypatch.setattr("fusion_cli.cli.repl.tui_loop.run_tui_repl", tui)
    monkeypatch.setattr(loop, "_read_line", satir_yok)

    kod = await loop.run_repl(
        make_config(), memory=null_memory(), root=tmp_path, console=Console(quiet=True)
    )

    assert kod == 0


# --- L2-08: canlı ayar birleşimi --------------------------------------------------------


def test_birlesim_oturum_degisikligini_korur_panel_degisikligini_alir():
    taban = make_config()
    oturum = replace(taban, agent=ModelSpec(name="oturum", model="sahte/oturum"))
    yuklenen = replace(taban, mcp_servers=())  # panelin değiştirdiği alan simülasyonu

    birlesik = rebase_session_changes(taban, oturum, replace(yuklenen, judge=taban.agent))

    assert birlesik.agent.model == "sahte/oturum"  # oturum değişikliği
    assert birlesik.judge == taban.agent  # panel değişikliği


def test_yenileme_oturumun_kendi_yazimini_degisiklik_saymaz(tmp_path):
    hedef = tmp_path / "config.yaml"
    config = replace(load_config(), source=hedef)
    from fusion_cli.config.writer import write_model_section

    write_model_section(config, hedef)
    state = _state(tmp_path, config=load_config(hedef))
    oturum = replace(state.config, agent=ModelSpec(name="x", model="nvidia_nim/x/oturum"))
    state.config = oturum
    write_model_section(oturum, hedef)  # oturumun KENDİ yazması dosya sürümünü değiştirir

    assert state.refresh_config() is False
    assert state.config.agent.model == "nvidia_nim/x/oturum"


def test_yenileme_panelin_mcp_eklemesini_alir_oturum_secimini_silmez(tmp_path):
    from fusion_cli.config.models import McpServerConfig

    hedef = tmp_path / "config.yaml"
    config = replace(load_config(), source=hedef)
    from fusion_cli.config.writer import write_model_section

    write_model_section(config, hedef)
    state = _state(tmp_path, config=load_config(hedef))
    state.config = replace(state.config, agent=ModelSpec(name="x", model="nvidia_nim/x/oturum"))

    # Panel (başka süreç) bir MCP sunucusu ekler.
    panel = replace(
        load_config(hedef),
        mcp_servers=(McpServerConfig(name="panel", command="npx", args=("-y", "x")),),
    )
    write_mcp_servers(panel, hedef)

    assert state.refresh_config() is True
    assert [sunucu.name for sunucu in state.config.mcp_servers] == ["panel"]
    assert state.config.agent.model == "nvidia_nim/x/oturum"


# --- L2-13: ağ çağrıları olay döngüsünü dondurmaz ----------------------------------------


async def test_development_katalog_getirme_olay_dongusunun_disinda_calisir(tmp_path, monkeypatch):
    from fusion_cli.cli.repl import model_flows
    from fusion_cli.providers.catalog import CatalogEntry

    state = _state(tmp_path)
    session = _TuiSession(state)
    ana_is_parcacigi = threading.get_ident()
    calisan: list[int] = []

    def getir():
        calisan.append(threading.get_ident())
        return (CatalogEntry(model_id="sahte/model", provider="sahte"),)

    kaynak = model_flows.Source("sahte", "Sahte", getir)
    monkeypatch.setattr(model_flows, "source_by_key", lambda config, key: kaynak)
    monkeypatch.setattr(
        model_flows,
        "apply_development_model",
        lambda config, model_id, paid: model_flows.FlowResult(config, "uygulandı"),
    )

    gorev = asyncio.ensure_future(session._run_development())
    await asyncio.sleep(0)
    session.tui._resolve("sahte")  # kaynak seçimi
    for _ in range(50):
        await asyncio.sleep(0.01)
        if calisan and session.tui._mode == "choice":
            break
    session.tui._resolve("sahte/model")  # model seçimi
    await gorev

    assert calisan and calisan[0] != ana_is_parcacigi
