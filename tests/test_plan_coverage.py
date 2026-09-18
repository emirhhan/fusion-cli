"""Plan, kullanıcının açıkça istediği teslimatları kapsamak zorundadır.

Ölçüldü (13 Eylül, Dead Cells koşusu): asset, UI ve ara sahne istendi; plan dört
adımdı ve hiçbiri bunları anmıyordu. Koşu "tamamlandı" raporladı, teslim edilen
şey iki sahne + dört script oldu.
"""

from __future__ import annotations

from fusion_cli.core.execution_plan import ExecutionPlan, PlanStep, RetrySafety
from fusion_cli.engines.agent.plan_coverage import (
    coverage_instruction,
    missing_deliverables,
)

GOREV = (
    "bana internetten free assetler toplayarak 2d bir oyun yapar mısın? hikayeler "
    "ara sahneler ve kaliteli bir UI olmalı"
)


def _adim(step_id: str, goal: str, *, kosul: str = "dosya yazıldı", etki: str = "file:a.gd"):
    return PlanStep(
        step_id=step_id,
        goal=goal,
        depends_on=(),
        expected_effects=(etki,),
        allowed_tool_families=("files",),
        success_criteria=(kosul,),
        verification_hint="",
        retry_safety=RetrySafety.SAFE,
    )


def _plan(*adimlar: PlanStep) -> ExecutionPlan:
    return ExecutionPlan(plan_id="p", task=GOREV, steps=adimlar)


def test_iskelet_plan_uc_teslimatin_eksikligini_bildirir():
    plan = _plan(
        _adim("discovery", "Çalışma dizinini incele"),
        _adim("create-project", "project.godot oluştur"),
        _adim("implement", "Oynanış sistemlerini kodla"),
        _adim("verify", "Projeyi derleyerek test et"),
    )

    eksikler = missing_deliverables(GOREV, plan)

    assert [t.name for t in eksikler] == [
        "dış varlık (asset) edinimi",
        "kullanıcı arayüzü (UI)",
        "hikâye / ara sahne",
    ]


def test_kapsayan_plan_eksik_bildirmez():
    plan = _plan(
        _adim("assets", "Ücretsiz sprite paketlerini indir ve manifeste yaz"),
        _adim("ui", "Ana menü ve HUD arayüzünü kur"),
        _adim("story", "Hikâye metnini ve ara sahne akışını yaz"),
    )

    assert missing_deliverables(GOREV, plan) == ()


def test_kapsam_basari_kosulundan_da_okunur():
    """Teslimat adım hedefinde değil başarı koşulunda anılıyorsa da kapsanmıştır."""
    plan = _plan(
        _adim("s1", "Varlıkları hazırla", kosul="assets/ASSETS.json manifesti doğrulandı"),
        _adim("s2", "Ekranları kur", kosul="menü sahnesi açılıyor"),
        _adim("s3", "Anlatı", kosul="cutscene akışı oynuyor"),
    )

    assert missing_deliverables(GOREV, plan) == ()


def test_istenmeyen_teslimat_zorunlu_tutulmaz():
    """Kapı yalnız AÇIKÇA istenen teslimatı arar; kendi başına iş eklemez."""
    gorev = "şu fonksiyondaki hatayı düzelt"
    plan = _plan(_adim("fix", "Hatayı düzelt"))

    assert missing_deliverables(gorev, plan) == ()


def test_onarim_metni_eklenecek_adimi_tarif_eder():
    """Eksiği adlandırmak yetmez; model aynı planı 'zaten kapsıyor' diye üretebilir."""
    eksikler = missing_deliverables(GOREV, _plan(_adim("implement", "Kodla")))

    metin = coverage_instruction(eksikler)

    assert "ÖNCEKİ PLANIN EKSİK" in metin
    assert "assets/ASSETS.json" in metin
    assert "ayrı adımlar olarak ekle" in metin


def _plan_json(*adimlar: tuple[str, str]) -> str:
    import json

    return json.dumps(
        {
            "plan_id": "p1",
            "task": GOREV,
            "steps": [
                {
                    "step_id": sid,
                    "goal": hedef,
                    "depends_on": [],
                    "expected_effects": ["file:x.gd"],
                    "allowed_tool_families": ["files"],
                    "success_criteria": ["dosya yazıldı"],
                    "verification_hint": "",
                    "retry_safety": "safe",
                }
                for sid, hedef in adimlar
            ],
        },
        ensure_ascii=False,
    )


async def test_eksik_kapsam_onarim_istemiyle_yeniden_sorulur(monkeypatch):
    """İlk plan eksikse model ikinci kez, EKSİK ADLARIYLA çağrılır."""
    from fusion_cli.engines.agent import plan_generation
    from fusion_cli.engines.agent.loop import AgentOutcome

    istemler: list[str] = []
    cevaplar = [
        _plan_json(("implement", "Oynanış sistemlerini kodla")),
        _plan_json(
            ("assets", "Ücretsiz sprite paketlerini indir ve manifeste yaz"),
            ("ui", "Ana menü ve HUD kur"),
            ("story", "Hikâye ve ara sahne akışını yaz"),
        ),
    ]

    async def _sahte_agent(prompt, deps, **kwargs):
        istemler.append(prompt)
        return AgentOutcome(final_text=cevaplar[len(istemler) - 1], messages=[], model_calls_made=1)

    sonuc = await plan_generation.generate_plan(
        GOREV, object(), _sahte_agent, 4, check_coverage=True
    )

    assert len(istemler) == 2
    assert "ÖNCEKİ PLANIN EKSİK" in istemler[1]
    assert sonuc.plan is not None
    assert sonuc.missing == ()


async def test_onarim_da_eksik_kalirsa_plan_calisir_ama_eksik_bildirilir(monkeypatch):
    """Çalışan planı çöpe atmak kullanıcıya hiçbir şey teslim etmemektir."""
    from fusion_cli.engines.agent import plan_generation
    from fusion_cli.engines.agent.loop import AgentOutcome

    async def _sahte_agent(prompt, deps, **kwargs):
        return AgentOutcome(
            final_text=_plan_json(("implement", "Oynanış sistemlerini kodla")),
            messages=[],
            model_calls_made=1,
        )

    sonuc = await plan_generation.generate_plan(
        GOREV, object(), _sahte_agent, 4, check_coverage=True
    )

    assert sonuc.plan is not None
    assert sonuc.missing == (
        "dış varlık (asset) edinimi",
        "kullanıcı arayüzü (UI)",
        "hikâye / ara sahne",
    )


async def test_yeniden_planlamada_kapsama_kapisi_calismaz():
    """Yeniden plan tek adımın yerine dal üretir; bütün teslimatları kapsamaz."""
    from fusion_cli.engines.agent import plan_generation
    from fusion_cli.engines.agent.loop import AgentOutcome

    cagri = 0

    async def _sahte_agent(prompt, deps, **kwargs):
        nonlocal cagri
        cagri += 1
        return AgentOutcome(
            final_text=_plan_json(("retry", "Adımı böl ve yeniden dene")),
            messages=[],
            model_calls_made=1,
        )

    sonuc = await plan_generation.generate_plan(GOREV, object(), _sahte_agent, 4)

    assert cagri == 1
    assert sonuc.plan is not None
    assert sonuc.missing == ()



def test_asset_adimina_sira_talimati_eklenir():
    """Manifest ÖNCE yazılırsa adım düşer; sıra kapı düşmeden önce söylenir.

    Ölçüldü (13 Eylül, iki ayrı Godot koşusu): model her ikisinde de manifesti ilk
    yazdı, hiç indirme yapmadı ve "manifest oluşturuldu" diye bildirdi.
    """
    from fusion_cli.core.execution_plan import VerificationCheck, VerificationCheckKind
    from fusion_cli.engines.agent.plan_context import asset_step, step_prompt

    adim = _adim("assets", "Ücretsiz assetleri topla", etki="file:ASSETS.json")
    adim = adim.__class__(
        **{
            **{alan: getattr(adim, alan) for alan in adim.__dataclass_fields__},
            "verification_checks": (
                VerificationCheck("assets", VerificationCheckKind.FILE_EXISTS, "ASSETS.json"),
            ),
        }
    )

    assert asset_step(adim)
    istem = step_prompt(adim, {})
    assert "ASSET SIRASI" in istem
    assert "manifesti EN SON" in istem
    assert '"files"' in istem


def test_asset_olmayan_adima_sira_talimati_eklenmez():
    from fusion_cli.engines.agent.plan_context import asset_step, step_prompt

    adim = _adim("code", "Oynanışı kodla", etki="file:scripts/player.gd")

    assert not asset_step(adim)
    assert "ASSET SIRASI" not in step_prompt(adim, {})


def test_gozlem_turunda_sira_talimati_verilmez():
    """Gözlem turunda indirme araçları kapalıdır; sıra talimatı yanıltıcı olur."""
    from fusion_cli.engines.agent.plan_context import step_prompt

    adim = _adim("assets", "Assetleri topla", etki="file:ASSETS.json")

    assert "ASSET SIRASI" not in step_prompt(adim, {}, observe=True)


async def test_planlanamayan_teslimat_turu_tamamlandi_saymaz(tmp_path):
    """Uyarı yetmez: "tamamlandı" görünen bir koşu teslim edilmemiş işi gizler.

    Ölçüldü (13 Eylül, Godot koşusu): asset, UI ve ara sahne istenmişti; plan iki
    adımdı, koşu yalnız `project.godot` yazıp "tamamlandı" raporladı.
    """
    from fusion_cli.core.execution_plan import ExecutionPlan
    from fusion_cli.engines.agent.loop import AgentOutcome
    from fusion_cli.engines.agent.plan_runner import run_execution_plan
    from tests.test_plan_repair import _deps
    from tests.test_plan_runner import _step

    deps = _deps(tmp_path)
    adim = _step("init", expected_effects=("file:project.godot",))

    async def agent(task, turn_deps, **kwargs):
        yol = tmp_path / "project.godot"
        turn_deps.tool_context.changes.record_created(yol)
        yol.write_text("[application]\n", encoding="utf-8")
        turn_deps.tool_context.touched.add(yol)
        return AgentOutcome(final_text="yazdım", messages=[], model_calls_made=1)

    sonuc = await run_execution_plan(
        GOREV,
        deps,
        agent,
        plan=ExecutionPlan("p", GOREV, (adim,)),
        self_review=False,
        uncovered=("dış varlık (asset) edinimi",),
    )

    assert sonuc.ok is False
    assert "teslim edilmedi" in sonuc.final_text
    assert "dış varlık (asset) edinimi" in sonuc.final_text


async def test_kullanilmayan_varlik_bulgusu_urunu_kuran_adimi_onarir(tmp_path):
    """Bulgu tek adımın kanıtını çürütmez; eksik olan ÜRÜNE bağlayan referanstır.

    Ölçüldü (13 Eylül, Godot koşusu): gerçek asset indirildi, proje ve menü
    yazıldı, Godot başsız açıldı — ama sahnede tek sprite yoktu. Kapı bunu
    yakaladı, onarılacak adım bulunamadığı için hiçbir deneme yapılmadı.
    """
    from fusion_cli.core.assets import UNUSED_ASSETS_PREFIX
    from fusion_cli.core.execution_plan import ExecutionPlan, PlanPhase
    from fusion_cli.core.verification import VerificationResult
    from fusion_cli.engines.agent.plan_context import workflow_budget
    from fusion_cli.engines.agent.plan_runner import _PlanRun
    from fusion_cli.engines.workflow.model import BudgetLedger
    from tests.test_plan_repair import _deps

    varlik_adimi = _adim("assets", "Varlıkları indir", etki="file:assets/ASSETS.json")
    urun_adimi = _adim("scenes", "Sahneleri yaz", etki="file:scenes/Main.tscn")
    urun_adimi = urun_adimi.__class__(
        **{
            **{alan: getattr(urun_adimi, alan) for alan in urun_adimi.__dataclass_fields__},
            "phase": PlanPhase.EXECUTION,
        }
    )
    deps = _deps(tmp_path)
    limits = workflow_budget(deps)
    kosu = _PlanRun(
        task=GOREV,
        deps=deps,
        agent=None,
        current=ExecutionPlan("p", GOREV, (varlik_adimi, urun_adimi)),
        limits=limits,
        ledger=BudgetLedger(limits),
    )

    kok = kosu._product_step_ids(
        VerificationResult(ok=False, summary=f"{UNUSED_ASSETS_PREFIX} assets/player.png")
    )

    # Varlığı GETİREN adım değil, sahneyi yazan adım onarılır.
    assert kok == {"scenes"}
    assert kosu._product_step_ids(VerificationResult(ok=False, summary="başka bir sorun")) == set()


def test_dosya_adi_gecen_bulgu_o_dosyayi_yazan_adimi_onarir(tmp_path):
    """Bulgu bir dosyayı adıyla suçluyorsa onarılacak adım bellidir.

    Ölçüldü (13 Eylül, Godot koşusu): kapı "main.gd: çalışma anında üretilen
    GDScript reload() edilmeden bağlanıyor" dedi; hiçbir adım köke bağlanamadığı
    için tek bir onarım denemesi bile yapılmadı ve koşu "kısmi" bitti.
    """
    from fusion_cli.core.execution_plan import ExecutionPlan
    from fusion_cli.core.verification import VerificationResult
    from fusion_cli.engines.agent.plan_context import workflow_budget
    from fusion_cli.engines.agent.plan_runner import _PlanRun
    from fusion_cli.engines.workflow.model import BudgetLedger
    from tests.test_plan_repair import _deps

    varlik = _adim("assets", "Varlıkları indir", etki="file:ASSETS.json")
    oyun = _adim("gameplay", "Oynanışı yaz", etki="file:main.gd")
    deps = _deps(tmp_path)
    limits = workflow_budget(deps)
    kosu = _PlanRun(
        task=GOREV,
        deps=deps,
        agent=None,
        current=ExecutionPlan("p", GOREV, (varlik, oyun)),
        limits=limits,
        ledger=BudgetLedger(limits),
    )
    bulgu = (
        "main.gd: çalışma anında üretilen GDScript `reload()` edilmeden "
        "`set_script()` ile bağlanıyor"
    )

    kok = kosu._product_step_ids(VerificationResult(ok=False, summary=bulgu, findings=(bulgu,)))

    assert kok == {"gameplay"}


def test_dosya_adi_gecmeyen_bulguda_eski_secim_korunur(tmp_path):
    from fusion_cli.core.assets import UNUSED_ASSETS_PREFIX
    from fusion_cli.core.execution_plan import ExecutionPlan, PlanPhase
    from fusion_cli.core.verification import VerificationResult
    from fusion_cli.engines.agent.plan_context import workflow_budget
    from fusion_cli.engines.agent.plan_runner import _PlanRun
    from fusion_cli.engines.workflow.model import BudgetLedger
    from tests.test_plan_repair import _deps

    varlik = _adim("assets", "Varlıkları indir", etki="file:assets/ASSETS.json")
    sahne = _adim("scenes", "Sahneleri yaz", etki="file:scenes/Main.tscn")
    sahne = sahne.__class__(
        **{
            **{alan: getattr(sahne, alan) for alan in sahne.__dataclass_fields__},
            "phase": PlanPhase.EXECUTION,
        }
    )
    deps = _deps(tmp_path)
    limits = workflow_budget(deps)
    kosu = _PlanRun(
        task=GOREV,
        deps=deps,
        agent=None,
        current=ExecutionPlan("p", GOREV, (varlik, sahne)),
        limits=limits,
        ledger=BudgetLedger(limits),
    )

    kok = kosu._product_step_ids(
        VerificationResult(ok=False, summary=f"{UNUSED_ASSETS_PREFIX} indirilen paket")
    )

    assert kok == {"scenes"}


def test_bildirilmeyen_ama_dokunulan_dosya_da_adima_baglanir(tmp_path):
    """Plan her dosyayı bildirmez; kanıt kaydı dokunulanı yine gösterir.

    Ölçüldü (13 Eylül, koşu 31): kapı `Player.tscn` için doğru bulguyu verdi ama
    hiçbir adım o yolu `expected_effects` içinde bildirmiyordu (adım yalnız
    `file:scenes/Main.tscn` diyordu). Eşleme boş kalınca tek bir onarım denemesi
    bile yapılmadı ve koşu "kısmi" bitti.
    """
    from fusion_cli.core.checkpoint import StepCheckpointEvidence
    from fusion_cli.core.evidence import ToolUse
    from fusion_cli.core.execution_plan import ExecutionPlan
    from fusion_cli.core.verification import VerificationResult
    from fusion_cli.engines.agent.plan_context import workflow_budget
    from fusion_cli.engines.agent.plan_runner import _PlanRun
    from fusion_cli.engines.workflow.model import BudgetLedger
    from tests.test_plan_repair import _deps

    varlik = _adim("assets", "Varlıkları indir", etki="file:ASSETS.json")
    oyun = _adim("gameplay", "Sahneleri yaz", etki="file:scenes/Main.tscn")
    deps = _deps(tmp_path)
    limits = workflow_budget(deps)
    kosu = _PlanRun(
        task=GOREV,
        deps=deps,
        agent=None,
        current=ExecutionPlan("p", GOREV, (varlik, oyun)),
        limits=limits,
        ledger=BudgetLedger(limits),
    )
    kosu.evidence["gameplay"] = StepCheckpointEvidence(
        step_id="gameplay",
        tool_uses=(
            ToolUse("write_file", arguments={"path": "scenes/Player.tscn"}, mutating=True),
        ),
    )
    bulgu = "Player.tscn: 'Player' düğümüne bağlı Player.gd script'i `$Sprite2D` kullanıyor"

    kok = kosu._product_step_ids(VerificationResult(ok=False, summary=bulgu, findings=(bulgu,)))

    assert kok == {"gameplay"}


DEADCELLS_GOREVI = GOREV + " deadcells e benzeyen bir oyun olsun"


def test_deadcells_istegi_dusman_adimi_zorunlu_kilar():
    """"Dead Cells benzeri" demek dövüş demektir.

    Ölçüldü (13 Eylül, koşu 32): oyun çalıştı, assetler ve hareket tamamdı;
    kullanıcının ilk cümlesi "düşman yok, saldıracağımız bir şey yok" oldu. Plan
    hiçbir adımda düşman anmamıştı ve kapsama kapısı bunu istemiyordu.
    """
    plan = _plan(
        _adim("assets", "Ücretsiz assetleri indir"),
        _adim("ui", "Ana menü ve HUD kur"),
        _adim("story", "Hikâye ve ara sahne akışını yaz"),
        _adim("player", "Oyuncu hareketini kodla"),
    )

    assert [t.name for t in missing_deliverables(DEADCELLS_GOREVI, plan)] == ["düşman ve dövüş"]


def test_dusman_adimi_varsa_eksik_bildirilmez():
    plan = _plan(
        _adim("assets", "Ücretsiz sprite paketlerini indir"),
        _adim("ui", "Menü ve HUD kur"),
        _adim("story", "Ara sahne akışını yaz"),
        _adim("combat", "Düşmanları üret ve dövüş hasarını kur"),
    )

    assert missing_deliverables(DEADCELLS_GOREVI, plan) == ()


def test_dovus_istemeyen_gorevde_dusman_zorunlu_degildir():
    gorev = "bu fonksiyondaki hatayı düzelt"

    assert missing_deliverables(gorev, _plan(_adim("fix", "Hatayı düzelt"))) == ()
