"""Kalıcı kullanım günlüğü, `/usage`, `fusion usage`, `fusion insights` (P-056).

Ölçüldü (31 Ekim): `/cost` yalnız bu oturumu gösteriyordu; 24s/7g pencereleri, alt
ajan/MCP/beceri atfı ve HTML rapor yoktu; `kullanim.durum` yalnız oturum sayacını taşıyordu.
"""

from __future__ import annotations

import json
from dataclasses import replace

from rich.console import Console
from typer.testing import CliRunner

from fusion_cli.appserver.usage import UsageMeter, usage_status
from fusion_cli.cli import app as app_module
from fusion_cli.config.loader import load_config
from fusion_cli.core.events import ModelCallFinished, SkillLoaded, ToolExecuted, ToolOutcome
from fusion_cli.core.types import ModelResult, TokenUsage
from fusion_cli.observability.insights_html import render_insights
from fusion_cli.observability.usage_log import (
    KIND_MODEL,
    UsageLog,
    mcp_server_of,
    open_usage_log,
    summarize,
)
from fusion_cli.ui.usage_view import print_usage

runner = CliRunner()
SIMDI = 1_800_000_000.0


def _model_event(*, role="agent", cost=0.01, agent_id="", background=False, tokens=100):
    result = ModelResult(
        name="agent",
        model="openrouter/x",
        text="ok",
        latency_ms=5,
        ok=True,
        usage=TokenUsage(
            prompt_tokens=tokens,
            completion_tokens=tokens // 2,
            cost_usd=cost,
            prompt_measured=True,
            completion_measured=True,
            cost_known=True,
        ),
    )
    return ModelCallFinished(role=role, result=result, background=background, agent_id=agent_id)


def _log(tmp_path, *, now=SIMDI):
    saat = {"t": now}
    return UsageLog(tmp_path / "usage.jsonl", session_id="s1", clock=lambda: saat["t"]), saat


def test_model_arac_ve_beceri_olaylari_jsonl_e_yazilir_istem_yazilmaz(tmp_path):
    log, _ = _log(tmp_path)

    log.handle(_model_event())
    log.handle(
        ToolExecuted(
            name="github__create_issue",
            args={"gizli": "sir"},
            outcome=ToolOutcome.OK,
            output="çıktı",
        )
    )
    log.handle(SkillLoaded(qualified_name="kod-inceleme", revision="1"))

    satirlar = [json.loads(line) for line in log.path.read_text(encoding="utf-8").splitlines()]
    assert [s["tur"] for s in satirlar] == ["model", "arac", "beceri"]
    assert satirlar[0]["maliyet_usd"] == 0.01 and satirlar[0]["model"] == "openrouter/x"
    assert satirlar[1]["sunucu"] == "github"
    assert "sir" not in log.path.read_text(encoding="utf-8")
    assert "çıktı" not in log.path.read_text(encoding="utf-8")


def test_mcp_sunucu_adi_arac_adindan_cikarilir():
    assert mcp_server_of("github__create_issue") == "github"
    assert mcp_server_of("read_file") == ""
    assert mcp_server_of("__x") == ""


def test_ozet_pencereler_ve_atif(tmp_path):
    log, saat = _log(tmp_path)
    saat["t"] = SIMDI - 10 * 86400  # 10 gün önce: yalnız 30 günde
    log.handle(_model_event(cost=1.0))
    saat["t"] = SIMDI - 2 * 86400  # 2 gün önce: 7g ve 30g
    log.handle(_model_event(cost=0.5, agent_id="alt-1"))
    saat["t"] = SIMDI - 3600  # 1 saat önce: hepsi
    log.handle(_model_event(cost=0.25, background=True))
    log.handle(ToolExecuted(name="linear__list", args={}, outcome=ToolOutcome.OK, output=""))
    log.handle(SkillLoaded(qualified_name="b", revision="1"))

    ozet = summarize(log.read(), now=SIMDI, session_id="s1")

    pencere = dict(ozet.windows)
    assert pencere["bu oturum"].calls == 3
    assert pencere["son 24 saat"].calls == 1
    assert pencere["son 7 gün"].calls == 2 and pencere["son 7 gün"].usage.cost_usd == 0.75
    assert pencere["son 30 gün"].calls == 3
    assert {row.label for row in ozet.by_actor} == {"alt ajan", "arka plan (hakem, sentez, ders)"}
    assert ozet.mcp_calls == (("linear", 1),)
    assert ozet.skills == (("b", 1),)


def test_baska_oturumun_kaydi_bu_oturuma_sayilmaz(tmp_path):
    log, _ = _log(tmp_path)
    log.handle(_model_event())
    diger = UsageLog(log.path, session_id="s2", clock=lambda: SIMDI)
    diger.handle(_model_event())

    ozet = summarize(diger.read(), now=SIMDI, session_id="s2")

    assert dict(ozet.windows)["bu oturum"].calls == 1
    assert dict(ozet.windows)["son 24 saat"].calls == 2


def test_eski_satirlar_budanir_ve_bozuk_satir_okumayi_dusurmez(tmp_path):
    log, saat = _log(tmp_path)
    saat["t"] = SIMDI - 100 * 86400
    log.handle(_model_event())
    saat["t"] = SIMDI
    log.handle(_model_event())
    with log.path.open("a", encoding="utf-8") as handle:
        handle.write("{bozuk\n")

    # Eski satır VE zaman damgası okunamayan bozuk satır atılır; sağlam yeni satır kalır.
    assert log.prune() == 2
    assert len(log.read()) == 1


def test_yazilamayan_gunluk_sessizce_kapanir(tmp_path):
    log = UsageLog(tmp_path / "yok" / "usage.jsonl", session_id="s", clock=lambda: SIMDI)
    (tmp_path / "yok").write_text("dosya", encoding="utf-8")  # dizin olamaz

    log.handle(_model_event())  # istisna yok
    assert log.read() == ()


def test_ayar_kapaliysa_gunluk_acilmaz():
    config = load_config()
    kapali = replace(config, runtime=replace(config.runtime, usage_log=False))

    assert open_usage_log(kapali) is None
    assert config.runtime.usage_log is True


def test_usage_tablosu_ve_kapali_notu(tmp_path):
    log, _ = _log(tmp_path)
    log.handle(_model_event())
    console = Console(record=True, width=120)

    print_usage(console, summarize(log.read(), now=SIMDI, session_id="s1"), log_path=str(log.path))
    metin = console.export_text()

    assert "bu oturum" in metin and "son 7 gün" in metin and "ana ajan" in metin
    console = Console(record=True, width=120)
    print_usage(console, summarize((), now=SIMDI, session_id=""), log_path=None)
    assert "kapalı" in console.export_text()


def test_kullanim_durum_rpc_gecmis_ve_atif_tasir(tmp_path):
    log, _ = _log(tmp_path)
    log.handle(_model_event(agent_id="alt"))
    log.handle(ToolExecuted(name="gh__x", args={}, outcome=ToolOutcome.OK, output=""))

    sonuc = usage_status(UsageMeter(), None, usage_log=log)

    assert sonuc["gunluk_acik"] is True
    assert [row["pencere"] for row in sonuc["gecmis"]] == ["son 24 saat", "son 7 gün", "son 30 gün"]
    assert sonuc["atif"]["kaynaklar"][0]["ad"] == "alt ajan"
    assert sonuc["atif"]["mcp"] == [{"ad": "gh", "cagri": 1}]
    assert usage_status(UsageMeter(), None)["gunluk_acik"] is False


def test_insights_html_turkce_ve_dis_kaynaksiz(tmp_path):
    log, _ = _log(tmp_path)
    log.handle(_model_event(cost=0.3))
    kayitlar = log.read()

    html = render_insights(summarize(kayitlar, now=SIMDI, session_id="s1"), kayitlar, now=SIMDI)

    assert html.startswith("<!doctype html>") and 'lang="tr"' in html
    assert "Kim harcadı" in html and "$0.3000" in html
    assert "http://" not in html and "https://" not in html


def test_fusion_insights_dosya_yazar_ve_usage_komutu_calisir(tmp_path, monkeypatch):
    config = load_config()
    monkeypatch.setattr(app_module, "load_config", lambda: replace(config, memory_dir=tmp_path))
    from fusion_cli.cli import usage_commands

    monkeypatch.setattr(usage_commands, "load_config", lambda: replace(config, memory_dir=tmp_path))
    log = UsageLog(tmp_path / "usage.jsonl", session_id="s", clock=lambda: SIMDI)
    log.handle(_model_event())

    hedef = tmp_path / "rapor.html"
    result = runner.invoke(app_module.app, ["insights", "--out", str(hedef)])
    assert result.exit_code == 0, result.output
    assert hedef.read_text(encoding="utf-8").startswith("<!doctype html>")

    result = runner.invoke(app_module.app, ["usage", "--days", "30"])
    assert result.exit_code == 0, result.output
    assert "son 30 gün" in result.output


def test_agent_komutu_gunlugu_besler(tmp_path, monkeypatch):
    """`fusion agent` gözlemcileri günlüğü de dinler: ModelCallFinished satıra iner."""
    from types import SimpleNamespace

    config = replace(load_config(), memory_dir=tmp_path)
    monkeypatch.setattr(app_module, "load_config", lambda: config)

    async def _sahte(task, cfg, *, sinks, **kwargs):
        for sink in sinks:
            sink.handle(_model_event())
        return SimpleNamespace(
            final_text="tamam", ok=True, budget_stopped=False, stop_reason=None, model_calls_made=1
        )

    monkeypatch.setattr(app_module, "run_agent_task", _sahte)
    result = runner.invoke(app_module.app, ["agent", "gorev", "--no-memory", "--quiet"])

    assert result.exit_code == 0, result.output
    satirlar = (tmp_path / "usage.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(satirlar) == 1 and json.loads(satirlar[0])["tur"] == KIND_MODEL


# --- İnceleme düzeltmeleri (31 Ekim): budama yarışı, tip doğrulama, oturum kimliği --- #


def test_budama_gerekmiyorsa_dosya_yeniden_yazilmaz(tmp_path):
    log, _ = _log(tmp_path)
    log.handle(_model_event())
    once = log.path.stat()

    assert log.prune() == 0
    sonra = log.path.stat()
    assert (sonra.st_ino, sonra.st_mtime_ns) == (once.st_ino, once.st_mtime_ns)


def test_budama_sirasinda_eklenen_satir_kaybolmaz(tmp_path, monkeypatch):
    """Başka süreç budama okuması ile yeniden yazma arasında satır eklerse o satır kalır."""
    log, saat = _log(tmp_path)
    saat["t"] = SIMDI - 100 * 86400
    log.handle(_model_event())
    saat["t"] = SIMDI
    log.handle(_model_event())
    diger = UsageLog(log.path, session_id="s2", clock=lambda: SIMDI)
    gercek = UsageLog._write_kept

    def _araya_giren(self, target, kept):
        diger.handle(_model_event())  # O_APPEND ile ikinci süreç
        gercek(self, target, kept)

    monkeypatch.setattr(UsageLog, "_write_kept", _araya_giren)

    assert log.prune() == 1
    assert sorted(record.oturum for record in log.read()) == ["s1", "s2"]


def test_tipi_bozuk_satir_atlanir_ozet_cokmez(tmp_path):
    log, _ = _log(tmp_path)
    log.handle(_model_event())
    with log.path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"ts": "dün", "oturum": "s1", "tur": "model"}) + "\n")
        handle.write(
            json.dumps({"ts": SIMDI, "oturum": "s1", "tur": "model", "girdi_token": "çok"}) + "\n"
        )
        handle.write(json.dumps({"ts": SIMDI, "oturum": 7, "tur": "model"}) + "\n")

    kayitlar = log.read(since=SIMDI - 10)
    ozet = summarize(log.read(), now=SIMDI, session_id="s1")

    assert len(kayitlar) == 1
    assert dict(ozet.windows)["bu oturum"].calls == 1


def test_masaustu_oturum_kimligi_nesne_adresine_dayanmaz(tmp_path, monkeypatch):
    """`masaustu-{id(self)}` yeniden başlatmada aynı adrese düşüp 'bu oturum'u şişirebiliyordu."""
    from fusion_cli.appserver import session as appserver_session

    kimlikler: list[str | None] = []

    def _kaydet(config, *, session_id=None):
        kimlikler.append(session_id)
        return None

    monkeypatch.setattr(appserver_session, "open_usage_log", _kaydet)
    oturum = appserver_session.AppSession(lambda _l: None, root=tmp_path, home=tmp_path / "ev")
    ikinci = appserver_session.AppSession(lambda _l: None, root=tmp_path, home=tmp_path / "ev")

    assert len(kimlikler) == 2 and kimlikler[0] != kimlikler[1]
    assert all(str(k).startswith("masaustu-") for k in kimlikler)
    assert kimlikler[0] != f"masaustu-{id(oturum)}" and kimlikler[1] != f"masaustu-{id(ikinci)}"
