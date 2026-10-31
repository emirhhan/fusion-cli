"""Ekip (P-061) ve iş akışı (P-062) bağımsız inceleme bulgularının regresyon testleri."""

from __future__ import annotations

import asyncio
import json

import pytest
from typer.testing import CliRunner

from fusion_cli.appserver.orchestration_routes import dispatch_orchestration
from fusion_cli.cli.team_cli import app as team_app
from fusion_cli.engines.agent.team_board import TeamBoard, TeamMember, TeamMessage, TeamStore


@pytest.fixture(autouse=True)
def _kullanici_dizini(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


def _kurban(root):
    """`.fusion/ekip/` dışında, içinde `pano.json` bulunan bir dizin (silinmemeli).

    `.fusion/ekip/../../kurban` tam olarak buraya çözülür.
    """
    # Ekip dizini var olmalı: yoksa işletim sistemi `..` geçişini zaten çözemez.
    (root / ".fusion" / "ekip").mkdir(parents=True)
    victim = root / "kurban"
    victim.mkdir()
    (victim / "pano.json").write_text(json.dumps({"name": "x", "members": []}), encoding="utf-8")
    (victim / "degerli.txt").write_text("silinmemeli", encoding="utf-8")
    return victim


@pytest.mark.parametrize(
    "ad", ["../../kurban", "../../kurban/", "..", "Büyük", "a/../../../kurban"]
)
def test_ekip_deposu_gecersiz_adla_yol_disina_cikmaz(tmp_path, ad):
    root = tmp_path / "proje"
    root.mkdir()
    victim = _kurban(root)
    store = TeamStore(root)

    assert store.delete(ad) is False
    assert store.load(ad) is None
    assert store.inbox(ad, "lider") == []
    assert (victim / "degerli.txt").is_file()


def test_ekip_deposu_gecerli_adla_siler_ve_alici_adini_dogrular(tmp_path):
    store = TeamStore(tmp_path)
    store.save(TeamBoard("site", "hedef", (TeamMember("kod"),)))
    store.append("site", TeamMessage("kod", "lider", "merhaba"))

    assert store.inbox("site", "../../site/pano") == []
    assert [m.text for m in store.inbox("site", "lider")] == ["merhaba"]
    assert store.delete("site") is True
    assert store.load("site") is None


async def test_ekip_sil_ve_pano_rpcsi_yol_gecisini_reddeder(tmp_path):
    root = tmp_path / "proje"
    root.mkdir()
    victim = _kurban(root)

    silme = await dispatch_orchestration("ekip.sil", {"ad": "../../kurban"}, root)
    pano = await dispatch_orchestration("ekip.pano", {"ad": "../../kurban"}, root)

    assert silme["ok"] is False and "ad" in silme["metin"].casefold()
    assert pano["ok"] is False
    assert (victim / "degerli.txt").is_file()


def test_fusion_ekip_sil_yol_gecisini_reddeder(tmp_path):
    root = tmp_path / "proje"
    root.mkdir()
    victim = _kurban(root)

    result = CliRunner().invoke(team_app, ["sil", "../../kurban", "--kok", str(root)])

    assert result.exit_code == 1
    assert (victim / "degerli.txt").is_file()


# -- görünürlük: Türkçe ek hâlleri ve devam turları ---------------------------- #

EKIP, AKIS = {"ekip"}, {"is_akisi"}


@pytest.mark.parametrize(
    ("cumle", "beklenen"),
    [
        ("Bir ajan takımı kur", EKIP),
        ("takımı oluştur ve işi böl", EKIP),
        ("ekibi kur", EKIP),
        ("ekibe görev ver", EKIP),
        ("ekibin raporunu özetle", EKIP),
        ("takımla birlikte çalış", EKIP),
        ("3 kişilik bir ajan ekibi kur", EKIP),
        ("spin up an agent team", EKIP),
        ("İŞ AKIŞI kur: 20 dosyayı incele", AKIS),
        ("iş akışını kaydet", AKIS),
        ("bunu alt ajanlarla paralel yap", AKIS),
        ("subagent fan out over the files", AKIS),
        ("kask ekipmanı stoğunu güncelle", set()),
        ("motosiklet ekipmanları sayfasını düzelt", set()),
        ("takip kodunu ekle", set()),
        ("bu dosyayı düzelt", set()),
    ],
)
def test_orkestrasyon_gorev_turleri_turkce_ek_halleriyle(cumle, beklenen):
    from fusion_cli.engines.agent.orchestration_tools import orchestration_task_kinds

    assert orchestration_task_kinds(cumle) == beklenen


def test_kayitli_ekip_varken_devam_turunda_ekip_araci_acik_kalir(tmp_path):
    from fusion_cli.engines.agent.orchestration_tools import orchestration_task_kinds

    assert orchestration_task_kinds("devam et", tmp_path) == set()
    TeamStore(tmp_path).save(TeamBoard("site", "hedef", (TeamMember("kod"),)))

    assert orchestration_task_kinds("devam et", tmp_path) == EKIP
    assert orchestration_task_kinds("site üzerinde sürdür", tmp_path) == EKIP
    assert orchestration_task_kinds("bu dosyayı düzelt", tmp_path) == set()


def test_kayitli_is_akisi_adi_anilinca_arac_acilir(tmp_path):
    from fusion_cli.engines.agent.orchestration_tools import orchestration_task_kinds
    from fusion_cli.engines.agent.workflow_spec import parse_workflow
    from fusion_cli.engines.agent.workflow_store import WorkflowStore

    WorkflowStore(tmp_path).save(parse_workflow({"ad": "haftalik-rapor", "adimlar": ["a"]}))

    assert orchestration_task_kinds("haftalik-rapor'u yeniden koştur", tmp_path) == AKIS
    assert orchestration_task_kinds("raporu düzelt", tmp_path) == set()


# -- ekip: yazma alanı kapısı ------------------------------------------------- #


def _uye_ajani(aktif: list[int], en_cok: list[int]):
    from types import SimpleNamespace

    from tests.test_agent_teams import _arac

    async def _ajan(task, sub_deps, **kwargs):
        aktif[0] += 1
        en_cok[0] = max(en_cok[0], aktif[0])
        try:
            alindi = await _arac(sub_deps, "team_task", eylem="al")
            await asyncio.sleep(0.03)
            if alindi.ok:
                kimlik = alindi.output.split()[0]
                await _arac(sub_deps, "team_task", eylem="bitir", id=kimlik, sonuc="tamam")
        finally:
            aktif[0] -= 1
        return SimpleNamespace(final_text="bitti", ok=True, tool_calls_made=1)

    return _ajan


def _ekip(uyeler):
    return {
        "ad": "kapi",
        "hedef": "kapı denemesi",
        "uyeler": uyeler,
        "gorevler": [{"baslik": f"İş {u['ad']}", "atanan": u["ad"]} for u in uyeler],
    }


async def test_ekipte_alani_belirsiz_yazarlar_ayni_anda_kosmaz(tmp_path):
    from fusion_cli.engines.agent.team_tools import team_run_tool
    from tests.fakes import RecordingSink
    from tests.test_agent_teams import _deps

    deps = _deps(tmp_path, RecordingSink())
    aktif, en_cok = [0], [0]
    istek = _ekip([{"ad": "kod"}, {"ad": "test"}])

    sonuc = await team_run_tool(deps, depth=0, run_agent=_uye_ajani(aktif, en_cok)).run(
        istek, deps.tool_context
    )

    assert sonuc.ok and "2/2 görev tamam" in sonuc.output, sonuc.output
    assert en_cok[0] == 1


async def test_ekipte_salt_okur_ve_ayrik_alanli_uyeler_eszamanli_kosar(tmp_path):
    from fusion_cli.engines.agent.team_tools import team_run_tool
    from tests.fakes import RecordingSink
    from tests.test_agent_teams import _deps

    deps = _deps(tmp_path, RecordingSink())
    aktif, en_cok = [0], [0]
    istek = _ekip(
        [
            {"ad": "okur", "salt_okunur": True},
            {"ad": "css", "yazma_alani": ["site/css"]},
            {"ad": "js", "yazma_alani": ["site/js"]},
        ]
    )

    sonuc = await team_run_tool(deps, depth=0, run_agent=_uye_ajani(aktif, en_cok)).run(
        istek, deps.tool_context
    )

    assert sonuc.ok and "3/3 görev tamam" in sonuc.output, sonuc.output
    assert en_cok[0] == 3


# -- beklenmedik istisna: koşu ve pano 'calisiyor' kalmaz ---------------------- #


async def test_kayit_yazilamasa_da_is_akisi_kosusu_biter(tmp_path, monkeypatch):
    from fusion_cli.core.orchestration_events import WorkflowProgress
    from tests.fakes import RecordingSink
    from tests.test_workflow_runtime import _calistir, _deps, _ok

    def _dolu_disk(self, record):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(
        "fusion_cli.engines.agent.workflow_store.WorkflowStore.write_run", _dolu_disk
    )
    sink = RecordingSink()

    async def _ajan(task, sub_deps, **kwargs):
        return _ok(f"<{task}>")

    sonuc, _ = await _calistir(
        _deps(tmp_path, sink), {"ad": "disk", "adimlar": ["bir", "iki"]}, run_agent=_ajan
    )

    assert sonuc.status == "tamam" and sonuc.agents == 2
    assert [o for o in sink.events if isinstance(o, WorkflowProgress)][-1].status == "tamam"


async def test_beklenmedik_istisnada_is_akisi_hata_durumuyla_kapanir(tmp_path, monkeypatch):
    from fusion_cli.core.orchestration_events import WorkflowProgress
    from tests.fakes import RecordingSink
    from tests.test_workflow_runtime import _calistir, _deps, _ok

    def _bozuk(*args, **kwargs):
        raise ValueError("beklenmedik")

    monkeypatch.setattr("fusion_cli.engines.agent.workflow_runtime.render_prompt", _bozuk)
    sink = RecordingSink()

    async def _ajan(task, sub_deps, **kwargs):
        return _ok(task)

    sonuc, store = await _calistir(
        _deps(tmp_path, sink), {"ad": "bozuk", "adimlar": ["bir"]}, run_agent=_ajan
    )

    assert sonuc.status == "hata" and "beklenmedik" in sonuc.report
    kayit = store.run(sonuc.run_id)
    assert kayit is not None and kayit.status == "hata" and kayit.finished_at > 0
    assert [o for o in sink.events if isinstance(o, WorkflowProgress)][-1].status == "hata"


async def test_beklenmedik_istisnada_ekip_panosu_calisiyor_kalmaz(tmp_path, monkeypatch):
    from fusion_cli.core.orchestration_events import TeamBoardChanged
    from fusion_cli.engines.agent.team_tools import team_run_tool
    from tests.fakes import RecordingSink
    from tests.test_agent_teams import _deps

    async def _bozuk(self, member):
        raise OSError(30, "Read-only file system")

    monkeypatch.setattr("fusion_cli.engines.agent.team_session.TeamSession.member_started", _bozuk)
    sink = RecordingSink()
    deps = _deps(tmp_path, sink)

    sonuc = await team_run_tool(deps, depth=0, run_agent=_uye_ajani([0], [0])).run(
        _ekip([{"ad": "kod", "salt_okunur": True}]), deps.tool_context
    )

    assert not sonuc.ok and "Read-only" in sonuc.output
    assert [o for o in sink.events if isinstance(o, TeamBoardChanged)][-1].status == "durdu"


# -- iş akışı planı ve boru hattı ---------------------------------------------- #


def test_otomatik_dugum_anahtari_kullanici_kimligiyle_cakismaz():
    from fusion_cli.engines.agent.workflow_plan import agents_in, bind_inputs, expand
    from fusion_cli.engines.agent.workflow_spec import parse_workflow

    spec = parse_workflow(
        {
            "ad": "cakisma",
            "adimlar": [{"ajan": "x", "id": "a2"}, "y", "z", {"ajan": "t", "id": "a4"}],
        }
    )
    anahtarlar = [ajan.key for ajan in agents_in(expand(spec, bind_inputs(spec, None)))]

    assert len(set(anahtarlar)) == 4, anahtarlar
    assert anahtarlar[0] == "a2" and anahtarlar[3] == "a4"


async def test_boru_hattinda_basarisiz_adimdan_sonrakiler_atlanir(tmp_path):
    from types import SimpleNamespace

    from tests.fakes import RecordingSink
    from tests.test_workflow_runtime import _calistir, _deps, _ok

    gorulen: list[str] = []

    async def _ajan(task, sub_deps, **kwargs):
        gorulen.append(task)
        if task == "bir":
            return SimpleNamespace(final_text="çöktü", ok=False, tool_calls_made=1)
        return _ok(task)

    sonuc, store = await _calistir(
        _deps(tmp_path, RecordingSink()),
        {
            "ad": "hat",
            "adimlar": [
                {
                    "paralel": [
                        {"sira": ["bir", "iki: {onceki}"]},
                        {"ajan": "kol", "salt_okunur": True},
                    ]
                },
                "son",
            ],
        },
        run_agent=_ajan,
    )

    # Kırılan yalnız `bir`in zinciri: paralel kardeş `kol` ve kolun bir kısmı başarılı
    # olduğu için son adım (kısmi sonuçla) yine koşar.
    assert sorted(gorulen) == ["bir", "kol", "son"], gorulen
    kayit = store.run(sonuc.run_id)
    assert kayit is not None
    assert [n.status for n in kayit.nodes] == ["basarisiz", "atlandi", "tamam", "tamam"]
    assert "önceki adım" in kayit.nodes[1].summary.casefold()
    assert sonuc.status == "yarim"


async def test_tum_kollari_basarisiz_paralel_adimdan_sonra_zincir_kesilir(tmp_path):
    from types import SimpleNamespace

    from tests.fakes import RecordingSink
    from tests.test_workflow_runtime import _calistir, _deps

    gorulen: list[str] = []

    async def _ajan(task, sub_deps, **kwargs):
        gorulen.append(task)
        return SimpleNamespace(final_text="çöktü", ok=False, tool_calls_made=1)

    sonuc, _ = await _calistir(
        _deps(tmp_path, RecordingSink()),
        {
            "ad": "hepsi",
            "adimlar": [{"paralel": [{"ajan": "a", "salt_okunur": True}, "b"]}, "c", "d"],
        },
        run_agent=_ajan,
    )

    assert sorted(gorulen) == ["a", "b"]
    assert sonuc.agents == 2 and sonuc.status == "yarim"


# -- tur geneli orkestrasyon tavanı ------------------------------------------- #


async def test_ayni_turda_art_arda_is_akisi_tur_tavanini_asamaz(tmp_path):
    from fusion_cli.engines.agent.workflow_tools import workflow_run_tool
    from tests.fakes import RecordingSink
    from tests.test_workflow_runtime import _deps, _ok

    deps = _deps(tmp_path, RecordingSink(), dynamic_workflow_max_agents=5)
    baslayan: list[str] = []

    async def _ajan(task, sub_deps, **kwargs):
        baslayan.append(task)
        return _ok(task)

    arac = workflow_run_tool(deps, depth=0, run_agent=_ajan)
    tanim = {"ad": "uc", "adimlar": [{"paralel": ["a", "b", "c"]}]}

    ilk = await arac.run({"tanim": tanim}, deps.tool_context)
    ikinci = await arac.run({"tanim": tanim}, deps.tool_context)

    assert ilk.ok, ilk.output
    assert not ikinci.ok and "tur" in ikinci.output and "5" in ikinci.output
    assert len(baslayan) == 3


async def test_tur_tavani_dolunca_ekip_baslamaz_kalan_payla_sinirlanir(tmp_path):
    from fusion_cli.engines.agent.team_tools import team_run_tool
    from tests.fakes import RecordingSink
    from tests.test_agent_teams import _deps

    deps = _deps(tmp_path, RecordingSink(), dynamic_workflow_max_agents=5, agent_team_max_runs=16)
    deps.child_runs.started_total = 5

    sonuc = await team_run_tool(deps, depth=0, run_agent=_uye_ajani([0], [0])).run(
        _ekip([{"ad": "kod", "salt_okunur": True}]), deps.tool_context
    )

    assert not sonuc.ok and "tur" in sonuc.output
    assert TeamStore(tmp_path).load("kapi") is None


# -- komut yüzeyi: alt komut gölgelemesi, ayrılmış adlar, sessiz ezme ----------- #


def _state(tmp_path):
    from tests.test_orchestration_surfaces import _state as surfaces_state

    return surfaces_state(tmp_path)


@pytest.mark.parametrize(
    "hedef",
    [
        "list the open PRs and review",
        "sil eski loglari temizle",
        "show me the API surface",
        "kur giriş sayfasını tasarla",
    ],
)
def test_team_alt_komut_kelimesiyle_baslayan_hedef_ekip_kurar(tmp_path, hedef):
    from fusion_cli.cli.repl.team_commands import team_command

    state = _state(tmp_path)

    cikti = team_command(state, hedef)

    assert "ekibi kuruyor" in cikti, cikti
    beklenen = hedef.removeprefix("kur ").strip()
    assert f"Hedef: {beklenen}" in state.pending_task


def test_team_alt_komutlari_kayitli_ekip_ve_tek_adla_calisir(tmp_path):
    from fusion_cli.cli.repl.team_commands import team_command

    TeamStore(tmp_path).save(TeamBoard("site", "hedef", (TeamMember("kod"),)))
    state = _state(tmp_path)

    assert "site" in team_command(state, "goster site")
    assert "adlı ekip yok" in team_command(state, "goster yok-boyle")
    assert "adlı ekip yok" in team_command(state, "sil yok-boyle")
    assert "/team kur" in team_command(state, "message the maintainers about it")
    assert state.pending_task == ""
    assert team_command(state, "mesaj site kod merhaba").startswith("'site' ekibi")
    assert state.pending_task.startswith("team_run aracıyla 'site'")
    assert team_command(state, "sil site") == "Silindi: site"


@pytest.mark.parametrize("ad", ["goster", "liste", "sil", "iptal", "list", "show"])
def test_ayrilmis_kelime_is_akisi_adi_olarak_kaydedilemez(tmp_path, ad):
    from fusion_cli.engines.agent.workflow_spec import WorkflowError, parse_workflow
    from fusion_cli.engines.agent.workflow_store import WorkflowStore

    with pytest.raises(WorkflowError, match="ayrılmış"):
        WorkflowStore(tmp_path).save(parse_workflow({"ad": ad, "adimlar": ["a"]}))


async def test_kaydet_ayni_adli_farkli_tanimi_sessizce_ezmez_basarisiz_kosuda_kaydetmez(tmp_path):
    from fusion_cli.engines.agent.workflow_spec import parse_workflow
    from fusion_cli.engines.agent.workflow_store import WorkflowStore
    from fusion_cli.engines.agent.workflow_tools import workflow_run_tool
    from tests.fakes import RecordingSink
    from tests.test_workflow_runtime import _deps, _ok

    store = WorkflowStore(tmp_path)
    elle = store.save(parse_workflow({"ad": "inceleme", "adimlar": ["elle yazılmış"]}))
    once = elle.read_text(encoding="utf-8")
    deps = _deps(tmp_path, RecordingSink())
    baslayan: list[str] = []

    async def _ajan(task, sub_deps, **kwargs):
        baslayan.append(task)
        return _ok(task)

    arac = workflow_run_tool(deps, depth=0, run_agent=_ajan)
    ezme = await arac.run(
        {"tanim": {"ad": "inceleme", "adimlar": ["modelin"]}, "kaydet": True}, deps.tool_context
    )

    assert not ezme.ok and "zaten kayıtlı" in ezme.output
    assert elle.read_text(encoding="utf-8") == once and baslayan == []

    async def _iptal(task, sub_deps, **kwargs):
        raise __import__("asyncio").CancelledError

    yeni = await workflow_run_tool(deps, depth=0, run_agent=_iptal).run(
        {"tanim": {"ad": "yeni-akis", "adimlar": ["x"]}, "kaydet": True}, deps.tool_context
    )

    assert "Kaydedildi" not in yeni.output
    assert store.find("yeni-akis") is None


# -- terminal: canlı pano yerine tek satırlık ilerleme ------------------------- #


def _renderer():
    import io

    from rich.console import Console

    from fusion_cli.ui.renderer import ConsoleRenderer

    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=200)
    return ConsoleRenderer(console, live_progress=False), buffer


def test_terminal_is_akisi_ilerlemesini_evre_ve_durum_degisince_basar():
    from fusion_cli.core.events import TurnFinished
    from fusion_cli.core.orchestration_events import WorkflowNodeView, WorkflowProgress

    renderer, buffer = _renderer()

    def _olay(status, phase, durumlar, started):
        nodes = tuple(WorkflowNodeView(f"a{i}", f"adım {i}", d) for i, d in enumerate(durumlar))
        return WorkflowProgress("k42", "inceleme", status, phase, started, 50, nodes)

    renderer.handle(_olay("calisiyor", "Keşif", ["bekliyor", "bekliyor", "bekliyor"], 0))
    renderer.handle(_olay("calisiyor", "Keşif", ["calisiyor", "bekliyor", "bekliyor"], 1))
    renderer.handle(_olay("calisiyor", "Rapor", ["tamam", "tamam", "calisiyor"], 3))
    renderer.handle(_olay("tamam", "Rapor", ["tamam", "tamam", "tamam"], 3))
    renderer.handle(TurnFinished())
    cikti = buffer.getvalue()

    assert "/workflows iptal k42" in cikti
    assert cikti.count("İş akışı 'inceleme' ·") == 3
    assert "evre: Rapor · 2/3 adım · 3/50 ajan" in cikti
    assert "tamamlandı · evre: Rapor · 3/3 adım" in cikti


def test_terminal_ekip_panosunu_gorev_ve_uye_durumu_degisince_basar():
    from fusion_cli.core.events import TurnFinished
    from fusion_cli.core.orchestration_events import (
        TeamBoardChanged,
        TeamMemberView,
        TeamTaskView,
    )

    renderer, buffer = _renderer()

    def _olay(status, gorevler, uyeler):
        return TeamBoardChanged(
            "site",
            "hedef",
            status,
            tasks=tuple(TeamTaskView(f"g{i}", "iş", d) for i, d in enumerate(gorevler)),
            members=tuple(TeamMemberView(ad, "", d) for ad, d in uyeler),
        )

    renderer.handle(_olay("calisiyor", ["bekliyor", "bekliyor"], [("kod", "calisiyor")]))
    renderer.handle(_olay("calisiyor", ["bekliyor", "bekliyor"], [("kod", "calisiyor")]))
    renderer.handle(_olay("calisiyor", ["tamam", "bekliyor"], [("kod", "sirada")]))
    renderer.handle(_olay("bitti", ["tamam", "tamam"], [("kod", "bitti")]))
    renderer.handle(TurnFinished())
    cikti = buffer.getvalue()

    assert cikti.count("Ekip 'site' ·") == 3
    assert "çalışıyor · 1/2 görev · kod sırada" in cikti
    assert "tamamlandı · 2/2 görev · kod bitti" in cikti
