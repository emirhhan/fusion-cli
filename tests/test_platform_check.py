"""Dış platforma bağlı istekte işe başlamadan resmi kaynak kontrolü."""

from __future__ import annotations

import pytest

from fusion_cli.core.events import PlatformChecked
from fusion_cli.engines.agent.platform_check import detect_platforms
from fusion_cli.tools import web

from .fakes import model_result
from .test_teacher_first import _setup


@pytest.mark.parametrize(
    ("task", "names"),
    [
        ("Instagram story paylaşan bir betik yaz", ("Instagram",)),
        ("Shopify ve TikTok ürün eşitlemesi kur", ("Shopify", "TikTok")),
        ("Google Ads kampanya raporunu çek", ("Google Ads",)),
        ("src/app.py dosyasındaki hatayı düzelt", ()),
    ],
)
def test_platform_tespiti(task: str, names: tuple[str, ...]) -> None:
    assert tuple(platform.name for platform in detect_platforms(task)) == names


async def test_resmi_kaynak_sonucu_ciraga_isten_once_verilir(monkeypatch, tmp_path) -> None:
    queries: list[str] = []

    def _fake_endpoint(query: str) -> list[str]:
        queries.append(query)
        return ["Stories: link, poll ve location çıkartmaları API ile desteklenmez."]

    monkeypatch.setattr(web, "SEARCH_ENDPOINTS", (_fake_endpoint,))
    deps, sink, _teacher, apprentice = _setup(
        monkeypatch,
        tmp_path,
        verified=False,
        apprentice_answers=[
            model_result("Link çıkartması API ile eklenemiyor; bildirimle yayın öneriyorum.")
        ],
    )

    await _run("Instagram story'ye link çıkartması ekleyen otomasyon kur", deps)

    assert queries and queries[0].startswith("site:developers.facebook.com Instagram API")
    first_context = "\n".join(message.content for message in apprentice.seen_messages[0])
    assert "API ile desteklenmez" in first_context
    assert "YAPILAMAYACAĞINI" in first_context
    checked = [event for event in sink.events if isinstance(event, PlatformChecked)]
    assert checked and checked[0].method == "resmi-kaynak"


async def test_kaynak_bulunamazsa_dogrulanmadigi_cevaba_yazilir(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(web, "SEARCH_ENDPOINTS", (lambda _query: [],))
    deps, sink, _teacher, _apprentice = _setup(
        monkeypatch,
        tmp_path,
        verified=False,
        apprentice_answers=[model_result("Story otomasyonu hazır.")],
    )

    result = await _run("Instagram story'ye link çıkartması ekleyen otomasyon kur", deps)

    assert "resmi kaynaktan doğrulanamadı" in result.final_text
    checked = [event for event in sink.events if isinstance(event, PlatformChecked)]
    assert checked[0].method == "dogrulanamadi"


async def test_ogretmen_kisiti_cevapta_yoksa_eklenir(monkeypatch, tmp_path) -> None:
    """Model kısıtı anmadan 'tamam' dese bile yapılamayan iş cevapta görünür."""
    monkeypatch.setattr(web, "SEARCH_ENDPOINTS", (lambda _query: ["resmi sayfa"],))
    plan = model_result(
        '{"adimlar":["Taslağı hazırla"],"dosyalar":[],"riskler":[],'
        '"yapilamayanlar":[{"konu":"Story çıkartması","gerekce":"API desteklemiyor",'
        '"alternatif":"Bildirimle yayınla"}],"dogrulama":[]}'
    )
    deps, _sink, _teacher, _apprentice = _setup(
        monkeypatch,
        tmp_path,
        teacher_answers=[plan],
        apprentice_answers=[model_result("Otomasyon tamamlandı.")],
    )

    result = await _run("Instagram API ile story çıkartması yayımlama akışını kur", deps)

    assert "Yapılamayan: Story çıkartması" in result.final_text
    assert "Bildirimle yayınla" in result.final_text


async def test_platformsuz_istekte_arama_yapilmaz(monkeypatch, tmp_path) -> None:
    calls: list[str] = []
    monkeypatch.setattr(web, "SEARCH_ENDPOINTS", (lambda query: calls.append(query) or [],))
    deps, sink, _teacher, _apprentice = _setup(monkeypatch, tmp_path, verified=False)

    await _run("src/app.py dosyasındaki hatayı düzelt", deps)

    assert calls == []
    assert not any(isinstance(event, PlatformChecked) for event in sink.events)


async def _run(task, deps):
    from fusion_cli.engines.agent.loop import run_agent

    return await run_agent(task, deps)
