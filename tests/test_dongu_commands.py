"""`fusion eval` ve `fusion prompt-opt`: döngünün üç halkası uçtan uca, GERÇEK MODEL ÇAĞRISI YOK.

Kullanıcı veri dizini conftest'in izole `XDG_DATA_HOME`'una düşer; gerçek istem dosyası
(`system.md`) testte `TARGETS` yamasıyla geçici bir dosyaya yönlendirilir ve dokunulmaz.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from evals.dongu_kaydi import kayitlari_oku
from evals.execution import TaskExecution
from evals.kume import kabul_edilen_kimlikler
from evals.loader import load_tasks
from prompt_opt.proposals import ProposalStore
from prompt_opt.targets import TARGETS, PromptTarget, get_target
from typer.testing import CliRunner

from fusion_cli.cli import dongu_commands
from fusion_cli.cli.app import app
from fusion_cli.cli.repl.transcript_store import TranscriptStore
from fusion_cli.config.loader import load_config
from fusion_cli.config.paths import loop_dir
from fusion_cli.core.events import Channel, TurnAnswered, TurnOutcome

runner = CliRunner()
EK = "Her değişiklikten sonra testi çalıştır ve sonucu bildir."
TEMEL = "Kurallar:\n1. Önce oku.\n2. Sonra yaz.\n3. Sonucu bildir.\n" * 6


def _konus(root: Path, mesajlar: list) -> None:
    """Gerçek günlük biçiminde (TranscriptStore) bir konuşma yaz."""
    root.mkdir(parents=True, exist_ok=True)
    store = TranscriptStore(load_config().memory_dir, root, conversation_id="oturum-1")
    for mesaj in mesajlar:
        store.record_user(mesaj) if isinstance(mesaj, str) else store.handle(mesaj)


def _hatali_konusma(root: Path) -> None:
    _konus(
        root,
        [
            "login.py içindeki parola kontrolünü düzelt",
            TurnAnswered(channel=Channel.MAIN, text="Düzelttim."),
            TurnOutcome(status="completed", elapsed_s=2.0),
            "hayır, yanlış yaptın; testler hâlâ düşüyor",
        ],
    )


def _kume_yaz(ad: str, kimlikler: list[str]) -> None:
    dizin = loop_dir() / "kume"
    dizin.mkdir(parents=True, exist_ok=True)
    gorevler = "".join(
        f"  - id: {k}\n    request: {k} için dosyayı düzelt ve bitir\n"
        "    criterion:\n      kind: keyword\n      keyword: tamam\n"
        for k in kimlikler
    )
    (dizin / f"{ad}.yaml").write_text(f"tasks:\n{gorevler}", encoding="utf-8")


# --------------------------------------------------------------------------- #
# Halka 1: hata → taslak → onay
# --------------------------------------------------------------------------- #


def test_taslak_hatti_uretir_listeler_kabul_ve_sil(tmp_path):
    proje = tmp_path / "proje"
    _hatali_konusma(proje)

    uret = runner.invoke(app, ["eval", "taslak-uret", "--proje", str(proje)])
    assert uret.exit_code == 0, uret.output
    assert "1 yeni yazıldı" in uret.output

    liste = runner.invoke(app, ["eval", "taslaklar"])
    assert "duzeltme" in liste.output
    kimlik = next(s.split()[1] for s in liste.output.splitlines() if "tk-" in s)
    # Otomatik kümeye GİRMEZ: kullanıcı kümesi henüz yok.
    assert not (loop_dir() / "kume").exists()

    # Ölçütsüz taslak kabul edilmez.
    reddedildi = runner.invoke(app, ["eval", "kabul", kimlik])
    assert reddedildi.exit_code == 1
    assert "ölçüt yok" in reddedildi.output.replace("\n", " ")

    kabul = runner.invoke(app, ["eval", "kabul", kimlik, "--anahtar", "parola doğrulandı"])
    assert kabul.exit_code == 0, kabul.output
    (gorev,) = load_tasks(loop_dir() / "kume" / "kullanici.yaml")
    assert gorev.request == "login.py içindeki parola kontrolünü düzelt"
    assert "tk-" in next(iter(kabul_edilen_kimlikler(loop_dir() / "kume")))

    # Kabul edilen aynı hata bir daha taslak olmaz.
    tekrar = runner.invoke(app, ["eval", "taslak-uret", "--proje", str(proje)])
    assert "0 yeni yazıldı" in tekrar.output

    olaylar = [k["olay"] for k in kayitlari_oku(loop_dir() / "kayit.jsonl")]
    assert olaylar.count("taslak_uretildi") == 2
    assert "taslak_kabul" in olaylar


def test_silinen_taslak_yeniden_onerilmez(tmp_path):
    proje = tmp_path / "proje"
    _hatali_konusma(proje)
    runner.invoke(app, ["eval", "taslak-uret", "--proje", str(proje)])
    liste = runner.invoke(app, ["eval", "taslaklar"])
    kimlik = next(s.split()[1] for s in liste.output.splitlines() if "tk-" in s)

    assert runner.invoke(app, ["eval", "sil", kimlik]).exit_code == 0
    assert (
        "0 yeni yazıldı"
        in runner.invoke(app, ["eval", "taslak-uret", "--proje", str(proje)]).output
    )
    assert "Onay bekleyen taslak yok" in runner.invoke(app, ["eval", "taslaklar"]).output


def test_olmayan_taslak_anlasilir_hata_verir():
    sonuc = runner.invoke(app, ["eval", "sil", "tk-0123456789"])
    assert sonuc.exit_code == 1
    assert "böyle bir taslak yok" in sonuc.output.replace("\n", " ")
    assert runner.invoke(app, ["eval", "kabul", "../x"]).exit_code == 1


def test_taslak_ayrintisi_kaniti_gosterir(tmp_path):
    proje = tmp_path / "proje"
    _hatali_konusma(proje)
    runner.invoke(app, ["eval", "taslak-uret", "--proje", str(proje)])
    kimlik = next(
        s.split()[1]
        for s in runner.invoke(app, ["eval", "taslaklar"]).output.splitlines()
        if "tk-" in s
    )
    ayrinti = runner.invoke(app, ["eval", "taslaklar", kimlik]).output
    assert "login.py" in ayrinti
    assert "yanlış yaptın" in ayrinti


# --------------------------------------------------------------------------- #
# Halka 2-3: öneri → onaylı uygulama → geri alma
# --------------------------------------------------------------------------- #


class _SahteEkSaglayici:
    def __init__(self) -> None:
        self.cagri = 0

    async def propose(self, base_text, failures, count):
        self.cagri += 1
        return (EK,)


class _SahteYurutucu:
    """Aday metinde EK varsa görev geçer; yoksa kalır."""

    def __init__(self, metin: str) -> None:
        self._metin = metin

    async def run(self, task):
        return TaskExecution(task_id=task.id, output_text="tamam" if EK in self._metin else "")


@pytest.fixture
def sahte_dongu(monkeypatch, tmp_path):
    """Gerçek model yerine sahte sağlayıcı/yürütücü; istem hedefi geçici dosya."""
    istem = tmp_path / "system.md"
    istem.write_text(TEMEL, encoding="utf-8")
    gercek = get_target("system")
    monkeypatch.setitem(
        TARGETS, "system", PromptTarget("system", istem, gercek.module, gercek.attribute)
    )
    saglayici = _SahteEkSaglayici()
    monkeypatch.setattr(dongu_commands, "_snippet_provider", lambda config: saglayici)
    monkeypatch.setattr(dongu_commands, "_executor_factory", lambda config, target: _SahteYurutucu)
    return istem, saglayici


def test_ayni_kume_asiri_uyum_diye_reddedilir_model_cagrilmaz(sahte_dongu):
    _, saglayici = sahte_dongu
    _kume_yaz("ortak", ["a", "b", "c"])
    sonuc = runner.invoke(app, ["prompt-opt", "calistir", "--kume", "ortak", "--ayri", "ortak"])
    assert sonuc.exit_code == 1
    assert "aynı görevleri" in sonuc.output.replace("\n", " ")
    assert saglayici.cagri == 0


def test_olmayan_kume_bilinenleri_sayar(sahte_dongu):
    _kume_yaz("var", ["a", "b", "c"])
    sonuc = runner.invoke(app, ["prompt-opt", "calistir", "--kume", "yok", "--ayri", "var"])
    assert sonuc.exit_code == 1
    assert "küme bulunamadı" in sonuc.output.replace("\n", " ")


def test_oneri_uygula_geri_al_zinciri(sahte_dongu):
    istem, saglayici = sahte_dongu
    _kume_yaz("optimizasyon", ["a", "b", "c", "d"])
    _kume_yaz("ayri", ["x", "y", "z"])

    calistir = runner.invoke(
        app, ["prompt-opt", "calistir", "--kume", "optimizasyon", "--ayri", "ayri"]
    )
    assert calistir.exit_code == 0, calistir.output
    assert "onerildi" in calistir.output
    assert saglayici.cagri == 1
    assert istem.read_text(encoding="utf-8") == TEMEL  # öneri istem dosyasını DEĞİŞTİRMEZ

    (oneri,) = ProposalStore(loop_dir() / "oneriler").list()
    assert (oneri.opt_base, oneri.opt_candidate) == (0.0, 1.0)
    assert (oneri.heldout_base, oneri.heldout_candidate) == (0.0, 1.0)
    assert EK in runner.invoke(app, ["prompt-opt", "oneriler", oneri.id]).output

    uygula = runner.invoke(app, ["prompt-opt", "uygula", oneri.id])
    assert uygula.exit_code == 0, uygula.output
    assert istem.read_text(encoding="utf-8") == oneri.candidate_text
    assert runner.invoke(app, ["prompt-opt", "uygula", oneri.id]).exit_code == 1  # ikinci kez olmaz

    geri = runner.invoke(app, ["prompt-opt", "geri-al", "system"])
    assert geri.exit_code == 0, geri.output
    assert istem.read_text(encoding="utf-8") == TEMEL

    olaylar = [k["olay"] for k in kayitlari_oku(loop_dir() / "kayit.jsonl")]
    assert olaylar == ["oneri", "oneri_uygulandi", "oneri_geri_alindi"]
    oneri_kaydi = kayitlari_oku(loop_dir() / "kayit.jsonl")[0]
    assert (oneri_kaydi["opt_skoru"], oneri_kaydi["heldout_skoru"]) == (1.0, 1.0)


def test_olmayan_oneri_ve_izin_disi_istem_anlasilir_hata_verir(sahte_dongu):
    assert runner.invoke(app, ["prompt-opt", "uygula", "on-0123456789"]).exit_code == 1
    _kume_yaz("a", ["a", "b", "c"])
    _kume_yaz("b", ["x", "y", "z"])
    sonuc = runner.invoke(
        app, ["prompt-opt", "calistir", "--kume", "a", "--ayri", "b", "--istem", "tools"]
    )
    assert sonuc.exit_code == 1
    assert "optimize edilemeyen" in sonuc.output.replace("\n", " ")


def test_kota_hatasi_olcum_durdu_koduyla_cikar(sahte_dongu, monkeypatch):
    from evals.runner import RateLimitedError

    _kume_yaz("a", ["a", "b", "c"])
    _kume_yaz("b", ["x", "y", "z"])

    class _Kotali:
        async def run(self, task):
            raise RateLimitedError("günlük kota doldu")

    monkeypatch.setattr(
        dongu_commands, "_executor_factory", lambda config, target: lambda metin: _Kotali()
    )
    sonuc = runner.invoke(app, ["prompt-opt", "calistir", "--kume", "a", "--ayri", "b"])
    assert sonuc.exit_code == dongu_commands.EXIT_MEASUREMENT_STOPPED
    assert "ÖLÇÜM DURDURULDU" in sonuc.output.replace("\n", " ")


def test_silinmis_sohbet_taslak_uretmez_ve_kimliksiz_olaylari_baskasina_yapismaz(tmp_path):
    """Silinen sohbet taslağa girmez; kimliksiz olayları sonraki sohbete yapışmaz."""
    from fusion_cli.cli.repl.transcript_store import delete_conversation

    proje = tmp_path / "proje"
    proje.mkdir()
    memory_dir = load_config().memory_dir
    silinen = TranscriptStore(memory_dir, proje, conversation_id="silinen")
    silinen.record_user("tüm modülleri yeni arayüze taşı lütfen")
    silinen.handle(TurnOutcome(status="failed", elapsed_s=1.0))
    delete_conversation(memory_dir, proje, "silinen")
    kalan = TranscriptStore(memory_dir, proje, conversation_id="kalan")
    kalan.record_user("bir README yaz ve sırala lütfen")
    kalan.handle(TurnOutcome(status="completed", elapsed_s=1.0))

    sonuc = runner.invoke(app, ["eval", "taslak-uret", "--proje", str(proje)])
    assert "0 taslak bulundu" in sonuc.output
