"""Zayıf modele görev türüne göre SABİT araç alt kümesi (yol haritası 4. adım).

Ölçüldü (30 Ekim): `build_registry()` 74 ad döndürür ama bunun 21'i `advertised=False`
takma addır (`bash`, `create_file`, `str_replace`, `view`...): modele şema olarak GİTMEZ,
yalnız gelen çağrıyı eşler. Sıkı yüzeydeki zayıf model buna rağmen 36 şema ve ~16,6 bin
karakter alıyordu; profil bunu görev türüne göre daraltır. Güçlü model değişmez.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from fusion_cli.core.events import ToolProfileExpanded, ToolSurfaceOffered
from fusion_cli.core.types import Message, ModelSpec
from fusion_cli.engines.agent import tool_profiles as profiller
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy, policy_for
from fusion_cli.engines.agent.loop import _permitted, run_agent
from fusion_cli.engines.agent.tool_surface import measure_surface
from fusion_cli.tools import build_registry

from .fakes import ScriptedProvider, make_config, model_result, tool_call
from .test_agent_loop import _deps, _kur

ZAYIF = ModelSpec(name="agent", model="yerel/kucuk", tags=("compact",))
GUCLU = ModelSpec(name="agent", model="x/buyuk")


@pytest.fixture
def sink():
    from .fakes import RecordingSink

    return RecordingSink()


def _tam_defter():
    """Motorun gerçekte kurduğu defter: yerleşikler + motora bağlı araçlar (preview, site...)."""
    from pathlib import Path

    from fusion_cli.core.desktop_settings import DesktopSettings
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
    from fusion_cli.engines.agent.engine_tools import build_agent_registry
    from fusion_cli.engines.agent.loop import AgentDeps

    from .agent_harness import Publisher
    from .fakes import AlwaysApprove, RecordingSink

    # Computer use Claude Code gibi varsayılan kapalı (#420); kapalıyken `desktop_*` ailesi
    # defterde hiç olmaz ve sıkı yüzeyin gizlediği tek yerleşik aile ölçüden düşer. Tam
    # yüzeyi ölçmek için açık kurulur.
    deps = AgentDeps(
        config=make_config(desktop=DesktopSettings(enabled=True)),
        publisher=Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=Path()),
    )
    return build_agent_registry(deps, depth=0, run_agent=None)


def _siki(*profiller_: str) -> ExecutionPolicy:
    return ExecutionPolicy(
        is_web=False, compact_tool_surface=True, max_external_tools=12, tool_profiles=profiller_
    )


def _adlar(registry, politika, kinds=frozenset()) -> set[str]:
    return set(_permitted(None, registry, politika, kinds))


# --- (a) takma adlar modele ayrı şema olarak gitmez ---------------------------------


def test_takma_adlar_kayitta_var_ama_sema_listesinde_yok():
    registry = build_registry()
    takma = set(registry.names()) - set(registry.advertised_names())

    sema_adlari = {s["function"]["name"] for s in registry.schemas()}

    assert {"bash", "create_file", "str_replace", "view", "view_file"} <= takma
    assert not takma & sema_adlari
    assert sema_adlari == set(registry.advertised_names())


def test_turun_sunulan_semalari_da_takma_ad_icermez():
    registry = _tam_defter()
    takma = set(registry.names()) - set(registry.advertised_names())

    for politika in (ExecutionPolicy(is_web=False), _siki(), _siki("soru")):
        sema_adlari = {s["function"]["name"] for s in registry.schemas(_adlar(registry, politika))}
        assert not takma & sema_adlari


# --- sınıflayıcı ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("istek", "beklenen"),
    [
        ("bu projede auth nasıl çalışıyor, src/auth.py dosyasını oku ve anlat", {"soru"}),
        ("README dosyasını incele ve özetle", {"soru"}),
        ("login.py içindeki hatayı düzelt ve testi çalıştır", {"kod"}),
        ("src/app.py dosyasına yeni bir fonksiyon ekle", {"kod"}),
        ("html5 canvas ile snake oyunu yap", {"medya"}),
        ("bir remotion videosu hazırla", {"medya"}),
        ("masaüstündeki Finder penceresini aç", {"masaustu"}),
    ],
)
def test_istek_turu_mevcut_siniflayicilarla_profile_eslenir(istek, beklenen):
    assert beklenen <= profiller.classify_tool_profiles(istek)


def test_belirsiz_istek_profil_uretmez():
    assert profiller.classify_tool_profiles("merhaba") == frozenset()
    assert profiller.classify_tool_profiles("tamam") == frozenset()


# --- konuşma boyunca kararlılık: ilk istek + yalnız genişleme -------------------------


def _kullanici(metin: str) -> Message:
    return Message("user", metin)


def test_konusma_profili_ilk_istekten_gelir_ve_belirsiz_devam_daraltmaz():
    gecmis = [
        _kullanici("login.py içindeki hatayı düzelt"),
        Message("assistant", "tamam"),
    ]

    onceki = profiller.conversation_tool_profiles("login.py içindeki hatayı düzelt", ())
    sonra = profiller.conversation_tool_profiles("tamam devam et", gecmis)

    assert onceki == ("kod",)
    assert sonra == onceki


def test_okuma_ile_baslayan_konusma_duzenleme_isteyince_yalniz_genisler():
    gecmis = [_kullanici("src/auth.py dosyasını oku ve anlat"), Message("assistant", "...")]

    ikinci = profiller.conversation_tool_profiles("şimdi login.py içindeki hatayı düzelt", gecmis)
    gecmis2 = [*gecmis, _kullanici("şimdi login.py içindeki hatayı düzelt")]
    ucuncu = profiller.conversation_tool_profiles("teşekkürler", gecmis2)

    assert ikinci == ("kod", "soru")
    assert ucuncu == ikinci


def test_ozet_ve_harness_notu_kullanici_istegi_sayilmaz():
    gecmis = [
        _kullanici("login.py içindeki hatayı düzelt"),
        Message("user", "FUSION_NOT: oyun yap", harness_note=True),
    ]

    assert profiller.conversation_tool_profiles("tamam", gecmis) == ("kod",)


# --- yüzey: profil gizlemeleri ---------------------------------------------------------


def test_soru_profili_yazma_tarayici_medya_ve_surusu_gizler():
    registry = _tam_defter()

    tam = _adlar(registry, _siki())
    soru = _adlar(registry, _siki("soru"))

    assert {"read_file", "list_dir", "glob", "search_code", "run_shell", "todo_write"} <= soru
    assert {"web_search", "web_fetch"} <= soru
    gizli = {"edit_file", "multi_edit", "write_file", "start_preview", "browser_open",
             "site_design", "clone_site", "optimize_image", "spawn_agents", "council"}  # fmt: skip
    assert not gizli & soru
    assert gizli <= tam


def test_kod_profili_duzenleme_ve_onizlemeyi_acik_tutar_tarayiciyi_gizler():
    registry = _tam_defter()

    kod = _adlar(registry, _siki("kod"))

    assert {"edit_file", "multi_edit", "write_file", "run_shell", "git", "start_preview"} <= kod
    assert not {"browser_open", "browser_click", "site_design", "clone_site", "council"} & kod


def test_birlesik_profil_ikisinin_birlesimini_gosterir():
    registry = _tam_defter()

    soru_kod = _adlar(registry, _siki("kod", "soru"))

    assert _adlar(registry, _siki("kod")) == soru_kod


def test_web_ve_medya_profilleri_kendi_araclarini_gosterir():
    registry = _tam_defter()

    web = _adlar(registry, _siki("web"))
    medya = _adlar(registry, _siki("medya"), frozenset({"oyun"}))

    assert {"browser_open", "site_design", "clone_site", "web_search"} <= web
    assert {"play_probe", "optimize_image", "start_preview", "write_file"} <= medya


def test_profil_yokken_yuzey_bugunku_siki_yuzeyle_ayni():
    registry = _tam_defter()

    assert _adlar(registry, _siki()) == _adlar(
        registry, ExecutionPolicy(is_web=False, compact_tool_surface=True, max_external_tools=12)
    )


def test_acikca_istenen_arac_profil_disinda_bile_gizlenmez():
    registry = _tam_defter()

    izinli = _permitted({"browser_open", "read_file"}, registry, _siki("soru"))

    assert "browser_open" in izinli


def test_profil_mcp_araclarina_dokunmaz():
    from fusion_cli.core.tools import Tool, ToolResult

    async def _noop(args, context):
        return ToolResult("ok")

    registry = _tam_defter()
    registry.register_or_replace(Tool(name="srv__a", description="d", parameters={}, run=_noop))

    assert "srv__a" in _adlar(registry, _siki("soru"))


def test_genisletme_isareti_profil_gizlemesini_kaldirir_siki_yuzeyi_degil():
    registry = _tam_defter()

    genis = _adlar(registry, _siki("soru"), frozenset({profiller.WIDENED_KIND}))

    assert "edit_file" in genis and "browser_open" in genis
    assert not any(ad.startswith(("desktop_", "chrome_")) for ad in genis)


# --- policy_for: yalnız zayıf modelde, ayarla kapanır -----------------------------------


def test_zayif_modelde_politika_profil_tasir():
    politika = policy_for(make_config(), ZAYIF, "login.py içindeki hatayı düzelt")

    assert politika.compact_tool_surface and politika.tool_profiles == ("kod",)


def test_guclu_modelde_profil_yok_davranis_degismez(monkeypatch):
    monkeypatch.setattr(
        "fusion_cli.engines.agent.context_budget.input_window_tokens", lambda model: 200_000
    )

    politika = policy_for(make_config(), GUCLU, "login.py içindeki hatayı düzelt")

    assert not politika.compact_tool_surface and politika.tool_profiles == ()


def test_ayar_kapaliysa_bugunku_siki_yuzey_kalir():
    config = make_config(runtime={"weak_model_tool_profiles": False})

    politika = policy_for(config, ZAYIF, "login.py içindeki hatayı düzelt")

    assert politika.compact_tool_surface and politika.tool_profiles == ()


def test_ayar_varsayilan_acik():
    from fusion_cli.config.loader import load_config

    assert load_config().runtime.weak_model_tool_profiles is True


def test_politika_gecmisten_ilk_istegi_okur():
    gecmis = [_kullanici("login.py içindeki hatayı düzelt"), Message("assistant", "bitti")]

    politika = policy_for(make_config(), ZAYIF, "tamam", history=gecmis)

    assert politika.tool_profiles == ("kod",)


# --- ölçüm -------------------------------------------------------------------------------


def test_yuzey_olcumu_sayi_ve_karakter_verir():
    registry = _tam_defter()
    semalar = registry.schemas(_adlar(registry, _siki("kod")))

    boyut = measure_surface(semalar)

    assert boyut.count == len(semalar)
    assert boyut.chars == len(json.dumps(semalar, ensure_ascii=False))


def test_profil_zayif_modelde_sema_sayisini_ve_karakteri_belirgin_azaltir():
    registry = _tam_defter()
    olcu = {
        ad: measure_surface(registry.schemas(_adlar(registry, politika)))
        for ad, politika in {
            "guclu": ExecutionPolicy(is_web=False),
            "siki": _siki(),
            "soru": _siki("soru"),
            "kod": _siki("kod"),
        }.items()
    }

    assert olcu["siki"].chars < olcu["guclu"].chars
    assert olcu["kod"].chars < olcu["siki"].chars * 0.8
    assert olcu["soru"].chars < olcu["siki"].chars * 0.5
    assert olcu["soru"].count < olcu["kod"].count < olcu["siki"].count


# --- döngü: iz olayı ve profil dışı çağrıda tek seferlik genişleme -----------------------


def _zayif_deps(tmp_path, sink, **runtime):
    return _deps(
        tmp_path, sink, agent=ZAYIF, task_model_map={}, runtime={"agent_max_steps": 10, **runtime}
    )


def _istek_adlari(istek) -> set[str]:
    return {s["function"]["name"] for s in istek}


async def test_dongu_her_model_cagrisinda_sunulan_yuzeyi_olay_olarak_yazar(
    monkeypatch, tmp_path, sink
):
    saglayici = _kur(monkeypatch, ScriptedProvider([model_result("cevap")]))

    await run_agent("login.py içindeki hatayı düzelt", _zayif_deps(tmp_path, sink))

    olaylar = [e for e in sink.events if isinstance(e, ToolSurfaceOffered)]
    # Kanıt kapısı ek model çağrıları açabilir: her çağrı bir olay bırakır.
    assert len(olaylar) == saglayici.calls
    olay = olaylar[0]
    gonderilen = saglayici.seen_requests[0]
    assert olay.count == len(gonderilen)
    assert olay.schema_chars == len(json.dumps(gonderilen, ensure_ascii=False))
    assert olay.profile == "kod" and olay.compact and not olay.widened
    assert "browser_open" not in _istek_adlari(gonderilen)
    assert "edit_file" in _istek_adlari(gonderilen)


async def test_guclu_model_olayi_profilsiz_yazar_ve_tam_listeyi_alir(monkeypatch, tmp_path, sink):
    monkeypatch.setattr(
        "fusion_cli.engines.agent.context_budget.input_window_tokens", lambda model: 200_000
    )
    saglayici = _kur(monkeypatch, ScriptedProvider([model_result("cevap")]))

    await run_agent("login.py içindeki hatayı düzelt", _deps(tmp_path, sink))

    olay = next(e for e in sink.events if isinstance(e, ToolSurfaceOffered))
    assert olay.profile == "" and not olay.compact
    assert {"browser_open", "site_design", "council"} <= _istek_adlari(saglayici.seen_requests[0])


async def test_profil_disi_arac_cagrilirsa_yuzey_bir_kez_genisler_ve_cagri_calisir(
    monkeypatch, tmp_path, sink
):
    saglayici = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("browser_tabs_list")]),
                model_result("bitti"),
            ]
        ),
    )

    await run_agent("login.py içindeki hatayı düzelt", _zayif_deps(tmp_path, sink))

    ilk, ikinci = (_istek_adlari(r) for r in saglayici.seen_requests[:2])
    assert "browser_tabs_list" not in ilk
    assert {"browser_tabs_list", "site_design", "edit_file"} <= ikinci
    genisleme = [e for e in sink.events if isinstance(e, ToolProfileExpanded)]
    assert [(e.tool, e.profile) for e in genisleme] == [("browser_tabs_list", "kod")]
    sunulan = [e for e in sink.events if isinstance(e, ToolSurfaceOffered)]
    assert [e.widened for e in sunulan[:2]] == [False, True]
    assert sunulan[1].count > sunulan[0].count


async def test_genisleme_ayar_kapaliyken_olmaz(monkeypatch, tmp_path, sink):
    _kur(
        monkeypatch,
        ScriptedProvider(
            [model_result(tool_calls=[tool_call("browser_tabs_list")]), model_result("x")]
        ),
    )

    await run_agent(
        "login.py içindeki hatayı düzelt",
        _zayif_deps(tmp_path, sink, weak_model_tool_profiles=False),
    )

    assert not [e for e in sink.events if isinstance(e, ToolProfileExpanded)]


def test_replace_ile_kurulan_politika_alani_korur():
    assert replace(_siki("kod"), is_web=True).tool_profiles == ("kod",)
