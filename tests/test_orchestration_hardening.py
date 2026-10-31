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
