"""Kilitlenme ÖZELLİĞİ — senaryo değil, iddia testi.

Tek bir iddia sınanır:

    Model sonunda geçerli bir hamle yaparsa, harness onu ENGELLEMEZ.

Kilitlenme bu iddianın ihlalidir: model toparlanır ama kapılar birbirini
kilitlediği için hamlesi hiç çalışmaz ve tur sıfır ilerlemeyle ölür. Kullanıcının
gördüğü "3 turdur ilerleme yok · tur sonlandırıldı" tam olarak budur.

Senaryo testi tek bir yolu korur; bu dosya SINIFI korur: `adversarial.DAVRANISLAR`
listesine yeni bir zayıf-model davranışı eklendiğinde buradaki tüm iddialar onu da
otomatik kapsar.
"""

from __future__ import annotations

import pytest

from fusion_cli.core.events import ToolOutcome
from fusion_cli.engines.agent.loop import run_agent

from . import adversarial
from .agent_harness import blocked_tools, install_provider, tool_events, web_deps
from .fakes import RecordingSink, ScriptedProvider

GOREV = "index.html oluştur ve içine gerçek içerik yaz"


@pytest.fixture
def sink() -> RecordingSink:
    return RecordingSink()


async def _kostur(davranis, monkeypatch, tmp_path, sink):
    """Bir düşmanca davranışı gerçek döngüde koştur."""
    # `mevcut.txt`: kör yazıcının ezmeye çalıştığı kullanıcı dosyası. Her koşuda
    # bulunur ki davranışlar arasında kurulum farkı olmasın.
    (tmp_path / "mevcut.txt").write_text("kullanıcının verisi", encoding="utf-8")
    install_provider(monkeypatch, ScriptedProvider(davranis()))
    deps = web_deps(tmp_path, sink)
    return await run_agent(GOREV, deps, verify=False)


# --------------------------------------------------------------------------- #
# ANA İDDİA — toparlanan model işini bitirebilmeli
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("ad", "davranis"), adversarial.DAVRANISLAR)
async def test_toparlanan_model_isini_bitirebilir(ad, davranis, monkeypatch, tmp_path, sink):
    """Kapılar modeli cezalandırabilir ama GEÇERLİ hamlesini engelleyemez."""
    await _kostur(davranis, monkeypatch, tmp_path, sink)

    hedef = tmp_path / adversarial.HEDEF_DOSYA
    assert hedef.exists(), (
        f"[{ad}] model geçerli hamleyi yaptı ama diske hiçbir şey inmedi — "
        f"kilitlenme. Bloklananlar: {blocked_tools(sink)}"
    )
    assert hedef.read_text(encoding="utf-8") == adversarial.HEDEF_ICERIK


@pytest.mark.parametrize(("ad", "davranis"), adversarial.DAVRANISLAR)
async def test_tur_sifir_ilerlemeyle_olmez(ad, davranis, monkeypatch, tmp_path, sink):
    """Boşta-tur kapısı, toparlanabilen bir modeli erken kesmemeli."""
    sonuc = await _kostur(davranis, monkeypatch, tmp_path, sink)

    assert sonuc.mutating_tool_calls_made > 0, (
        f"[{ad}] tur hiç değişiklik üretmeden bitti — bloklananlar: {blocked_tools(sink)}"
    )


@pytest.mark.parametrize(("ad", "davranis"), adversarial.DAVRANISLAR)
async def test_kullanicinin_dosyasi_hicbir_davranista_ezilmez(
    ad, davranis, monkeypatch, tmp_path, sink
):
    """Kilit açmak KORUMAYI gevşetmemeli: kör yazma her koşulda engellenir."""
    await _kostur(davranis, monkeypatch, tmp_path, sink)

    korunan = (tmp_path / "mevcut.txt").read_text(encoding="utf-8")
    assert korunan == "kullanıcının verisi", f"[{ad}] kullanıcının dosyası ezildi"


# --------------------------------------------------------------------------- #
# ENGELLEME MESAJI — her kapı çıkış yolunu GÖSTERMEK zorunda
# --------------------------------------------------------------------------- #

#: Bir engelleme mesajının "çıkış yolu" saydığı işaretler: ya somut bir araç adı
#: ya da modelin yapabileceği açık bir eylem.
_CIKIS_ISARETLERI = (
    "read_file",
    "edit_file",
    "multi_edit",
    "write_file",
    "list_dir",
    "search_code",
    "browser_read",
    "browser_open",
    "browser_type",
    "ask_user",
    "run_shell",
    "sonraki adım",
    "farklı",
    "söyle",
)


@pytest.mark.parametrize(("ad", "davranis"), adversarial.DAVRANISLAR)
async def test_her_engelleme_cikis_yolu_gosterir(ad, davranis, monkeypatch, tmp_path, sink):
    """Çıkışsız engelleme mesajı kilitlenmenin KÖK SEBEBİDİR.

    Ölçülen olayda `write_file` "edit_file kullan" dedi ama edit_file o durumda
    çalışamıyordu; tekrar kapısı ise "bir sonraki adımı at" deyip hangi adım
    olduğunu söylemedi. Model yasal hamlesiz kaldı.
    """
    await _kostur(davranis, monkeypatch, tmp_path, sink)

    for olay in tool_events(sink):
        if olay.outcome not in (ToolOutcome.BLOCKED, ToolOutcome.FAILED):
            continue
        assert any(isaret in olay.output for isaret in _CIKIS_ISARETLERI), (
            f"[{ad}] '{olay.name}' engellendi ama çıkış yolu göstermedi:\n{olay.output}"
        )


# --------------------------------------------------------------------------- #
# BÜTÇE — tur her koşulda SONLANIR
# --------------------------------------------------------------------------- #


async def test_hic_toparlanmayan_model_turu_sonlandirir(monkeypatch, tmp_path, sink):
    """Karşı uç: model hiç düzelmezse tur sonsuza kadar sürmemeli, temiz bitmeli."""
    inatci = model_bozuk = None
    from .fakes import model_result, tool_call

    inatci = [model_result(tool_calls=(tool_call("list_dir", path="."),))] * 30
    del model_bozuk
    install_provider(monkeypatch, ScriptedProvider(inatci))
    deps = web_deps(tmp_path, sink)

    sonuc = await run_agent(GOREV, deps, verify=False)

    assert not sonuc.ok, "hiç ilerlemeyen tur başarılı sayılmamalı"
    assert sonuc.hit_step_limit, "bütçe kapısı devreye girmeliydi"


async def test_hic_toparlanmayan_turdan_ders_cikarilmaz(monkeypatch, tmp_path, sink):
    """Öz-zehirlenme kapısı bu sınıfta da tutmalı."""
    from .fakes import model_result, tool_call

    cagrildi = False

    async def _ders_cikar(*args, **kwargs):
        nonlocal cagrildi
        cagrildi = True
        return ()

    from fusion_cli.engines.agent import loop as agent_loop

    monkeypatch.setattr(agent_loop.learning_steps.learning, "extract_lessons", _ders_cikar)
    install_provider(
        monkeypatch,
        ScriptedProvider([model_result(tool_calls=(tool_call("list_dir", path="."),))] * 30),
    )
    deps = web_deps(tmp_path, sink, lessons=True)

    await run_agent(GOREV, deps, verify=False)

    assert not cagrildi
