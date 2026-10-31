"""Headless parite (P-026): `fusion agent` betik bayrakları, stdin görevi, bütçe tavanı,
JSON-Lines onay kanalı ve yapısal çıktı.

Ölçüldü (31 Ekim): `fusion agent` yalnız --mode/--no-memory/--json/--quiet/--add-dir
alıyordu; görev konumsal ve zorunluydu, maliyet tavanı ve araç izin listesi yoktu.
"""

from __future__ import annotations

import asyncio
import io
import json
from dataclasses import replace
from types import SimpleNamespace

from typer.testing import CliRunner

from fusion_cli.cli import app as app_module
from fusion_cli.cli.headless import (
    JsonLinesPrompter,
    OutputFormat,
    parse_tool_list,
    read_task,
    structured_result,
)
from fusion_cli.config.loader import load_config
from fusion_cli.core.budget import BudgetStop, TurnBudget
from fusion_cli.core.json_schema import validate_instance
from fusion_cli.core.tools import Tool, ToolContext
from fusion_cli.core.types import TokenUsage
from fusion_cli.engines.agent.approval import ApprovalAnswer, ApprovalRequest, Decision
from fusion_cli.engines.agent.tool_filter import DeniedToolsPolicy
from fusion_cli.memory.null import NullLessonMemory

runner = CliRunner()


class _Saat:
    def monotonic(self) -> float:
        return 0.0

    def now(self) -> float:
        return 0.0


def _butce(**overrides) -> TurnBudget:
    limits = {
        "max_model_calls": 50,
        "max_verify_rounds": 2,
        "max_empty_retries": 2,
        "max_contract_repairs": 1,
        "max_auto_continues": 1,
        "max_idle_rounds": 3,
    }
    limits.update(overrides)
    return TurnBudget(clock=_Saat(), **limits)


def _agent(monkeypatch, args: list[str], *, sonuc=None, input: str | None = None):
    """`run_agent_task`'ı sahteyle değiştir; çağrı argümanlarını ve çıktıyı döndür."""
    yakalanan: dict[str, object] = {}

    async def _sahte(task, config, **kwargs):
        yakalanan["task"] = task
        yakalanan["config"] = config
        yakalanan.update(kwargs)
        return sonuc or SimpleNamespace(
            final_text="tamam", ok=True, budget_stopped=False, stop_reason=None, model_calls_made=1
        )

    monkeypatch.setattr(app_module, "run_agent_task", _sahte)
    result = runner.invoke(app_module.app, ["agent", *args, "--no-memory", "--quiet"], input=input)
    return yakalanan, result


# --- maliyet tavanı (--max-budget-usd) ------------------------------------------------ #


def test_maliyet_tavani_asilinca_butce_doldu_sayilir():
    butce = _butce(max_cost_usd=0.01)
    butce.reserve_model_call()
    butce.usage.record(
        1, TokenUsage(prompt_tokens=1, completion_tokens=1, cost_usd=0.02, cost_known=True)
    )

    assert butce.cost_exhausted
    assert BudgetStop.COST_LIMIT.value == "cost_limit"


def test_maliyet_tavani_yoksa_hic_dolmaz():
    butce = _butce()
    butce.reserve_model_call()
    butce.usage.record(1, TokenUsage(cost_usd=99.0, cost_known=True))

    assert not butce.cost_exhausted


def test_bilinmeyen_maliyet_tavani_doldurmaz():
    """Ücretsiz/ölçülmemiş modelde maliyet bilinmez; tavan sıfır sayılıp tur kesilmez."""
    butce = _butce(max_cost_usd=0.0001)
    butce.reserve_model_call()
    butce.usage.record(1, TokenUsage(cost_usd=0.0, cost_known=False))

    assert not butce.cost_exhausted


def test_durma_nedeni_metni_turkce():
    from fusion_cli.ui.turn_stop import turn_stopped_summary

    assert "maliyet" in turn_stopped_summary("cost_limit", ()).lower()


def test_varsayilan_yapilandirmada_maliyet_tavani_yok():
    runtime = load_config().runtime
    assert runtime.agent_max_cost_usd is None
    assert runtime.project_instructions is True


# --- stdin görevi ----------------------------------------------------------------------- #


def test_tire_gorevi_stdin_den_okur():
    assert read_task("-", io.StringIO("  stdin görevi \n"), is_tty=False) == "stdin görevi"


def test_bos_gorev_boru_hattinda_stdin_den_okur():
    assert read_task("", io.StringIO("boru"), is_tty=False) == "boru"


def test_bos_gorev_terminalde_bos_kalir():
    assert read_task("", io.StringIO("yazilmaz"), is_tty=True) == ""


def test_agent_komutu_stdin_gorevini_motora_verir(monkeypatch):
    yakalanan, result = _agent(monkeypatch, ["-"], input="dosyaları listele\n")

    assert result.exit_code == 0, result.output
    assert yakalanan["task"] == "dosyaları listele"


# --- bayraklar yapılandırmaya/oturuma geçer -------------------------------------------- #


def test_max_turns_ve_butce_yapilandirmaya_gecer(monkeypatch):
    yakalanan, _ = _agent(monkeypatch, ["gorev", "--max-turns", "3", "--max-budget-usd", "0.5"])

    assert yakalanan["config"].runtime.agent_max_steps == 3
    assert yakalanan["config"].runtime.agent_max_cost_usd == 0.5


def test_arac_listeleri_virgul_ve_tekrarla_ayrilir():
    assert parse_tool_list(["read_file,grep", " run_shell "]) == frozenset(
        {"read_file", "grep", "run_shell"}
    )
    assert parse_tool_list(None) is None


def test_allowed_ve_disallowed_tools_oturuma_gecer(monkeypatch):
    yakalanan, _ = _agent(
        monkeypatch,
        ["gorev", "--allowed-tools", "read_file,grep", "--disallowed-tools", "run_shell"],
    )

    assert yakalanan["allowed_tools"] == {"read_file", "grep"}
    assert yakalanan["denied_tools"] == frozenset({"run_shell"})


def test_append_system_prompt_sisteme_eklenir(monkeypatch):
    yakalanan, _ = _agent(monkeypatch, ["gorev", "--append-system-prompt", "Kısa yaz."])

    assert "Kısa yaz." in yakalanan["extra_system"]


def test_bare_bellek_mcp_ve_talimatlari_kapatir(monkeypatch):
    yakalanan, _ = _agent(monkeypatch, ["gorev", "--bare"])

    config = yakalanan["config"]
    assert config.mcp_servers == ()
    assert config.hosted_connectors == ()
    assert config.runtime.project_instructions is False
    assert isinstance(yakalanan["memory"].lessons, NullLessonMemory)


def test_agent_tanimi_sistem_metni_ve_arac_setini_verir(monkeypatch, tmp_path):
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    (tmp_path / ".claude" / "agents" / "gozden-gecirici.md").write_text(
        "---\nname: gozden-gecirici\ndescription: kod inceler\ntools: Read, Grep\n---\n"
        "Sen bir kod gözden geçiricisin.",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    yakalanan, result = _agent(monkeypatch, ["gorev", "--agent", "gozden-gecirici"])

    assert result.exit_code == 0, result.output
    assert "kod gözden geçiricisin" in yakalanan["extra_system"]
    assert yakalanan["allowed_tools"] is not None
    assert "read_file" in yakalanan["allowed_tools"]


def test_bilinmeyen_agent_tanimi_hata_verir(monkeypatch):
    _, result = _agent(monkeypatch, ["gorev", "--agent", "olmayan-ajan"])

    assert result.exit_code != 0
    assert "olmayan-ajan" in result.output


# --- çıktı biçimleri -------------------------------------------------------------------- #


def test_bilinmeyen_output_format_reddedilir(monkeypatch):
    _, result = _agent(monkeypatch, ["gorev", "--output-format", "xml"])

    assert result.exit_code != 0


def test_output_format_json_tek_sonuc_nesnesi_basar(monkeypatch):
    _, result = _agent(monkeypatch, ["gorev", "--output-format", "json"])

    satirlar = [line for line in result.output.splitlines() if line.strip()]
    assert len(satirlar) == 1, result.output
    nesne = json.loads(satirlar[0])
    assert nesne["type"] == "result"
    assert nesne["ok"] is True
    assert nesne["sonuc"] == "tamam"
    assert nesne["durum"] == "completed"
    assert "kullanim" in nesne


def test_stream_json_ilk_satir_system_init(monkeypatch):
    _, result = _agent(monkeypatch, ["gorev", "--output-format", "stream-json"])

    ilk = json.loads(result.output.splitlines()[0])
    assert ilk["event"] == "SystemInit"
    assert ilk["kip"] == "auto"
    assert "model" in ilk


def test_eski_json_bayragi_stream_json_ile_ayni(monkeypatch):
    _, result = _agent(monkeypatch, ["gorev", "--json"])

    assert json.loads(result.output.splitlines()[0])["event"] == "SystemInit"


def test_output_format_enum_degerleri():
    assert {item.value for item in OutputFormat} == {"text", "json", "stream-json"}


# --- --json-schema ------------------------------------------------------------------------ #


def test_json_schema_dogrulayici_tip_zorunlu_alan_ve_enum():
    schema = {
        "type": "object",
        "required": ["ad", "puan"],
        "properties": {
            "ad": {"type": "string"},
            "puan": {"type": "integer"},
            "durum": {"type": "string", "enum": ["acik", "kapali"]},
            "etiketler": {"type": "array", "items": {"type": "string"}},
        },
    }
    assert validate_instance({"ad": "x", "puan": 3}, schema) == []
    hatalar = validate_instance({"ad": 5, "durum": "yok", "etiketler": [1]}, schema)
    assert any("puan" in hata for hata in hatalar)
    assert any("ad" in hata for hata in hatalar)
    assert any("durum" in hata for hata in hatalar)
    assert any("etiketler" in hata for hata in hatalar)


def test_yapisal_sonuc_kod_citi_icindeki_jsonu_ayiklar():
    sonuc = structured_result('Sonuç:\n```json\n{"ad": "x"}\n```', {"type": "object"})

    assert sonuc.value == {"ad": "x"}
    assert sonuc.errors == ()


def test_yapisal_sonuc_json_degilse_hata_listesi_dolu():
    sonuc = structured_result("merhaba", {"type": "object"})

    assert sonuc.value is None
    assert sonuc.errors


def test_json_schema_uyumsuz_cevap_basarisiz_cikis_ve_hata_listesi(monkeypatch, tmp_path):
    sema = tmp_path / "sema.json"
    sema.write_text(json.dumps({"type": "object", "required": ["ad"]}), encoding="utf-8")

    yakalanan, result = _agent(
        monkeypatch,
        ["gorev", "--json-schema", str(sema), "--output-format", "json"],
        sonuc=SimpleNamespace(
            final_text="merhaba",
            ok=True,
            budget_stopped=False,
            stop_reason=None,
            model_calls_made=1,
        ),
    )

    assert result.exit_code == 1
    nesne = json.loads(result.output.strip().splitlines()[-1])
    assert nesne["yapisal_hatalar"]
    assert "ad" in yakalanan["extra_system"]  # şema modele talimat olarak gider


def test_json_schema_uyumlu_cevap_yapisal_alani_doldurur(monkeypatch, tmp_path):
    sema = tmp_path / "sema.json"
    sema.write_text(json.dumps({"type": "object", "required": ["ad"]}), encoding="utf-8")

    _, result = _agent(
        monkeypatch,
        ["gorev", "--json-schema", str(sema), "--output-format", "json"],
        sonuc=SimpleNamespace(
            final_text='{"ad": "x"}',
            ok=True,
            budget_stopped=False,
            stop_reason=None,
            model_calls_made=1,
        ),
    )

    assert result.exit_code == 0
    nesne = json.loads(result.output.strip().splitlines()[-1])
    assert nesne["yapisal"] == {"ad": "x"}


# --- JSON-Lines onay kanalı (--permission-channel stdin) ---------------------------------- #


def _istek(name: str = "run_shell") -> ApprovalRequest:
    tool = Tool(name=name, description="", parameters={}, run=None, mutating=True)  # type: ignore[arg-type]
    return ApprovalRequest(tool=tool, args={"command": "ls"}, danger=None)


def _prompter(girdi: str) -> tuple[JsonLinesPrompter, io.StringIO]:
    cikti = io.StringIO()
    return JsonLinesPrompter(stdin=io.StringIO(girdi), stdout=cikti), cikti


def test_onay_kanali_istegi_yazar_ve_karari_okur():
    prompter, cikti = _prompter('{"istek_id": "1", "karar": "onayla"}\n')

    karar = asyncio.run(prompter.confirm(_istek()))

    assert karar is ApprovalAnswer.ONCE
    satirlar = [json.loads(line) for line in cikti.getvalue().splitlines()]
    assert satirlar[0]["event"] == "ApprovalRequested"
    assert satirlar[0]["arac"] == "run_shell"
    assert satirlar[0]["istek_id"] == "1"
    assert satirlar[-1]["event"] == "ApprovalResolved"


def test_onay_kanali_reddet_ve_oturum_kararlari():
    prompter, _ = _prompter(
        '{"istek_id": "1", "karar": "reddet"}\n{"istek_id": "2", "karar": "oturum"}\n'
    )

    assert asyncio.run(prompter.confirm(_istek())) is ApprovalAnswer.DENY
    assert asyncio.run(prompter.confirm(_istek())) is ApprovalAnswer.SESSION


def test_onay_kanali_eof_ve_yanlis_kimlik_sorulamadi_sayilir():
    prompter, _ = _prompter("")
    assert asyncio.run(prompter.confirm(_istek())) is ApprovalAnswer.UNAVAILABLE

    prompter, _ = _prompter('{"istek_id": "99", "karar": "onayla"}\n')
    assert asyncio.run(prompter.confirm(_istek())) is ApprovalAnswer.UNAVAILABLE


def test_onay_kanali_soru_cevabini_okur():
    prompter, cikti = _prompter('{"istek_id": "1", "cevap": "evet, devam"}\n')

    cevap = asyncio.run(prompter.ask("Devam edilsin mi?"))

    assert cevap == "evet, devam"
    assert json.loads(cikti.getvalue().splitlines()[0])["event"] == "QuestionAsked"


def test_onay_kanali_stdin_gorevle_birlikte_kullanilamaz(monkeypatch):
    _, result = _agent(monkeypatch, ["-", "--permission-channel", "stdin"], input="gorev")

    assert result.exit_code != 0


# --- --disallowed-tools politikası --------------------------------------------------------- #


class _HepIzin:
    async def decide(self, request):
        return Decision.ALLOW


def test_yasakli_arac_sorulmadan_engellenir_digerleri_ice_gider():
    policy = DeniedToolsPolicy(_HepIzin(), frozenset({"run_shell"}))

    assert asyncio.run(policy.decide(_istek("run_shell"))) is Decision.BLOCKED
    assert asyncio.run(policy.decide(_istek("read_file"))) is Decision.ALLOW


def test_oturum_yasakli_araclari_politikaya_sarar(monkeypatch, tmp_path):
    """`run_agent_task(denied_tools=…)` kurulan politikayı sarar (kırmızı: parametre yoktu)."""
    from fusion_cli.cli import session as session_module

    yakalanan = {}

    async def _sahte_run_agent(task, deps, **kwargs):
        yakalanan["policy"] = deps.policy
        return SimpleNamespace(
            final_text="ok",
            ok=True,
            budget_stopped=False,
            made_no_changes=False,
            stop_reason=None,
            tool_calls_made=0,
            mutating_tool_calls_made=0,
        )

    monkeypatch.setattr(session_module, "run_agent", _sahte_run_agent)
    monkeypatch.setattr(session_module, "suggest_followups", lambda evidence: ())
    monkeypatch.setattr(session_module, "evidence_from_turn", lambda *a, **k: None)
    config = replace(load_config(), mcp_servers=(), hosted_connectors=())

    asyncio.run(
        session_module.run_agent_task(
            "gorev",
            config,
            sinks=(),
            prompter_factory=lambda flush: None,
            root=tmp_path,
            tool_context=ToolContext(root=tmp_path),
            denied_tools=frozenset({"run_shell"}),
        )
    )

    assert isinstance(yakalanan["policy"], DeniedToolsPolicy)
