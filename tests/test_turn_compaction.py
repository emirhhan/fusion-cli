"""Tur içi bağlam yönetimi: önce eski çıktılar, sonra özet, taşma döngüsünde dur.

Kaynak: Claude Code belgesi ("How Claude Code works" › When context fills up) —
eski araç çıktıları önce temizlenir, gerekirse konuşma özetlenir; tek bir dev
çıktı bağlamı her özetten hemen sonra doldurursa birkaç denemeden sonra durulur.
"""

from __future__ import annotations

import pytest

from fusion_cli.core.budget import BudgetStop
from fusion_cli.core.events import ContextCompressed
from fusion_cli.core.types import Message
from fusion_cli.engines.agent import compaction, history
from fusion_cli.engines.agent import context_budget as budget_module
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent.context_budget import ContextBudget
from fusion_cli.engines.agent.loop import run_agent

from .fakes import ScriptedProvider, model_result, tool_call
from .test_agent_loop import _deps, _kur


def _konusma(cikti_sayisi: int, cikti: str = "x" * 1_000) -> list[Message]:
    mesajlar = [Message("system", "kimlik"), Message("user", "büyük görev")]
    for index in range(cikti_sayisi):
        cagri = tool_call("read_file", path=f"{index}")
        mesajlar.append(Message("assistant", "", tool_calls=(cagri,)))
        mesajlar.append(Message("tool", cikti, name="read_file", tool_call_id=str(index), ok=True))
    return mesajlar


def test_eski_arac_ciktilari_esige_kadar_temizlenir_son_cikti_korunur():
    mesajlar = _konusma(15)

    temiz = history.clear_old_tool_outputs(mesajlar, threshold_chars=8_000)

    assert len(temiz) == len(mesajlar)
    assert history.total_chars(temiz) < 8_000
    assert temiz[3].content.startswith("[eski araç çıktısı bağlamdan temizlendi")
    assert temiz[-1].content == "x" * 1_000
    assert temiz[1].content == "büyük görev"
    assert [m.tool_call_id for m in temiz] == [m.tool_call_id for m in mesajlar]


def test_esik_altindaysa_hicbir_cikti_temizlenmez():
    mesajlar = _konusma(3)

    assert history.clear_old_tool_outputs(mesajlar, threshold_chars=100_000) == mesajlar


def test_buyuk_ama_az_sayida_cikti_da_temizlenir():
    """Ölçüldü: 24 KB'lık birkaç okuma 20 mesajlık pencereye sığıyor, hiçbiri
    temizlenemiyordu."""
    mesajlar = _konusma(4, cikti="b" * 24_000)

    temiz = history.clear_old_tool_outputs(mesajlar, threshold_chars=30_000)

    assert history.total_chars(temiz) < 30_000
    assert temiz[-1].content == "b" * 24_000


def test_tur_ici_baslik_sistem_ve_gorevdir():
    mesajlar = [
        Message("system", "kimlik"),
        Message("user", "not", harness_note=True),
        Message("user", "görev"),
        Message("assistant", "..."),
    ]

    assert history.task_anchor_length(mesajlar) == 3


def test_tur_kesimi_arac_cagrisini_sonucundan_ayirmaz():
    mesajlar = _konusma(10)

    cut = history.round_cut(mesajlar, keep_recent=5)

    assert mesajlar[cut].role == "assistant"


async def test_temizlik_yeterliyse_ozet_istenmez(monkeypatch):
    async def _ozet(*_args, **_kwargs):
        raise AssertionError("temizlik yetince özet çağrılmamalı")

    monkeypatch.setattr(compaction, "_summarize", _ozet)
    mesajlar = _konusma(30)

    sonuc = await compaction.compact_in_turn(mesajlar, config=None, threshold_chars=25_000)

    assert history.total_chars(sonuc) < 25_000
    assert sonuc[:2] == mesajlar[:2]


async def test_temizlik_yetmezse_ara_adimlar_ozetlenir_gorev_korunur(monkeypatch):
    async def _ozet(*_args, **_kwargs):
        return "okunan dosyalar ve kararlar"

    monkeypatch.setattr(compaction, "_summarize", _ozet)
    mesajlar = _konusma(30, cikti="y" * 100)

    sonuc = await compaction.compact_in_turn(mesajlar, config=None, threshold_chars=1_000)

    assert sonuc[:2] == mesajlar[:2]
    assert sonuc[2].content.startswith("[önceki adımların özeti]")
    assert sonuc[2].harness_note is True
    assert sonuc[-1] == mesajlar[-1]
    assert len(sonuc) < len(mesajlar)


def _dar_esik(monkeypatch, esik: int) -> None:
    monkeypatch.setattr(
        budget_module, "context_budget", lambda _config, spec: ContextBudget(esik, None, "m")
    )


async def test_uzun_turda_baglam_tur_bitmeden_sikistirilir(monkeypatch, tmp_path, sink):
    """Ölçüldü (28 Eylül): sıkıştırma yalnız tur bitince yapılıyordu; uzun tek
    turda geçmiş sınırsız büyüdü."""
    for index in range(8):
        (tmp_path / f"d{index}.txt").write_text("z" * 3_000, encoding="utf-8")
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                *[
                    model_result(tool_calls=[tool_call("read_file", path=f"d{index}.txt")])
                    for index in range(8)
                ],
                model_result("Tüm dosyalar okundu ve özetlendi; değişiklik gerekmedi."),
            ]
        ),
    )

    async def _ozet(*_args, **_kwargs):
        return "özet"

    monkeypatch.setattr(compaction, "_summarize", _ozet)
    # API modelleri sistem metninde ayrıca kapsamlı talimat katmanını taşır
    # (`API_SYSTEM_PROMPT`). Yapay dar eşik bu sabit payı da içermeli; aksi hâlde
    # sıkıştırma sonrası bile bağlam dolu kalır ve tur "context_thrash" ile kesilir.
    from fusion_cli.engines.agent.loop import API_SYSTEM_PROMPT

    _dar_esik(monkeypatch, 12_000 + len(API_SYSTEM_PROMPT))

    sonuc = await run_agent(
        "dosyaları incele", _deps(tmp_path, sink, runtime={"agent_max_steps": 50})
    )

    assert any(isinstance(e, ContextCompressed) for e in sink.events)
    # Sekiz okumanın toplamı (24.000 karakter) geçmişte birikmez.
    assert history.total_chars(sonuc.messages) < 8 * 3_000
    assert sonuc.final_text.startswith("Tüm dosyalar okundu")


async def test_baglam_her_sikistirmadan_sonra_doluysa_dongu_kurulmaz(monkeypatch, tmp_path, sink):
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("list_dir", path=f"k{index}")])
                for index in range(20)
            ]
        ),
    )

    async def _degismez(messages, **_kwargs):
        return messages

    monkeypatch.setattr(compaction, "compact_in_turn", _degismez)
    _dar_esik(monkeypatch, 1)

    sonuc = await run_agent("görev", _deps(tmp_path, sink))

    assert sonuc.stop_reason == BudgetStop.CONTEXT_THRASH.value
    assert sonuc.model_calls_made < agent_loop.MAX_COMPACTION_THRASH + 1


@pytest.fixture
def sink():
    from .fakes import RecordingSink

    return RecordingSink()
