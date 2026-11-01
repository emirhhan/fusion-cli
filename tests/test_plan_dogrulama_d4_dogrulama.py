"""Dalga 4 (plan-dogrulama): adım doğrulama, kapı ve rapor bulguları (A4-14 ...)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fusion_cli.core.evidence import EvidenceStatus, ToolUse
from fusion_cli.core.execution_plan import VerificationCheck, VerificationCheckKind
from fusion_cli.core.lesson_runtime import LessonRuntimeContext
from fusion_cli.engines.agent import step_verification as sv
from fusion_cli.engines.agent.loop import AgentOutcome

from .fakes import make_config

# --- A4-14: git seçenekli çağrılarda alt komut doğru çıkarılır -------------------- #


@pytest.mark.parametrize(
    "komut",
    [
        "git --git-dir=.git commit -m x",
        "git -c a=b -C repo commit -m x",
        "git -C repo commit -m x",
        "git --no-pager commit -m x",
    ],
)
def test_git_secenekli_commit_tanınır(komut):
    """Ölçüldü (29 Ekim): `--git-dir=.git` değer-içi seçenekte `commit` atlanıyordu."""
    assert sv._contains_git_action(komut, "commit")


def test_git_baska_alt_komut_commit_sayilmaz():
    assert not sv._contains_git_action("git --git-dir=.git status", "commit")


# --- A4-53: 'var' alt dizesi ------------------------------------------------------ #


def test_eski_dosya_kosulu_varsayilan_kelimesine_takilmaz():
    from fusion_cli.core.execution_plan import PlanStep, RetrySafety

    adim = PlanStep(
        step_id="a",
        goal="g",
        depends_on=(),
        expected_effects=("file:a.txt",),
        allowed_tool_families=("files",),
        success_criteria=("dosya varsayılan ayarları içerir",),
        verification_hint="",
        retry_safety=RetrySafety.SAFE,
    )

    assert sv._legacy_file_check(adim, "dosya varsayılan ayarları içerir") is None
    assert sv._legacy_file_check(adim, "a.txt dosyası var") is not None


# --- A4-18: araç takma adı, boş expected, komut boşluğu --------------------------- #


def _cikti(*kullanimlar):
    return AgentOutcome("", [], tool_uses=tuple(kullanimlar))


def _kullanim(name, arguments=None, output=""):
    return ToolUse(name=name, ok=True, arguments=arguments or {}, output=output)


def test_arac_kontrolu_takma_adi_ve_bos_expected_kabul_eder(tmp_path):
    kontrol = VerificationCheck("k", VerificationCheckKind.TOOL, "bash", "")
    kanit = sv._evaluate_check(
        kontrol,
        root=tmp_path,
        outcome=_cikti(_kullanim("run_shell", {"command": "ls"})),
        verification=None,
    )

    assert kanit.status is EvidenceStatus.PASSED


def test_komut_kontrolu_bosluk_farkini_tolere_eder(tmp_path):
    kontrol = VerificationCheck("k", VerificationCheckKind.COMMAND, "pytest   -q")
    kanit = sv._evaluate_check(
        kontrol,
        root=tmp_path,
        outcome=_cikti(_kullanim("run_shell", {"command": "python3 -m pytest -q"})),
        verification=None,
    )

    assert kanit.status is EvidenceStatus.PASSED


# --- A4-19: içerik kontrolü ------------------------------------------------------- #


def test_dosya_icerik_kontrolu_bosluk_farkini_tolere_eder_ve_kesifte_dusurmez(tmp_path):
    (tmp_path / "a.py").write_text("def main() -> None:\n    pass\n", encoding="utf-8")
    kontrol = VerificationCheck("k", VerificationCheckKind.FILE_CONTAINS, "a.py", "def  main()")
    assert sv.evaluate_file_check(kontrol, tmp_path).status is EvidenceStatus.PASSED

    yanlis = VerificationCheck("k", VerificationCheckKind.FILE_CONTAINS, "a.py", "def run():")
    assert sv.evaluate_file_check(yanlis, tmp_path).status is EvidenceStatus.FAILED
    assert (
        sv.evaluate_file_check(yanlis, tmp_path, step_mutates=False).status
        is EvidenceStatus.UNVERIFIED
    )


# --- A4-17: değişken gürültü önceden kırık kapıyı yeni kırılma yapmaz -------------- #


def test_zaman_damgasi_ve_sure_farki_yeni_bulgu_sayilmaz():
    onceki = (
        "pytest düştü (çıkış 1)\n[2026-10-29 10:00:00] 3 failed in 1.52s pid 123 /tmp/tmpab/x",
    )
    simdi = (
        "pytest düştü (çıkış 1)\n[2026-10-29 10:07:41] 3 failed in 2.08s pid 9981 /tmp/tmpzz/x",
    )

    assert sv.new_findings(simdi, onceki) == ()
    yeni = ("pytest düştü (çıkış 1)\n[2026-10-29 10:07:41] 4 failed in 2.08s pid 9981",)
    assert sv.new_findings(yeni, onceki) == yeni


# --- A4-15: manifest taraması bağımlılık klasörlerine girmez ----------------------- #


def test_manifest_taramasi_node_modules_a_girmez(tmp_path):
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "node_modules" / "x" / "paket.json").write_text("{}", encoding="utf-8")
    (tmp_path / "ASSETS.json").write_text("{}", encoding="utf-8")

    adlar = [p.name for p in sv._manifests(tmp_path)]

    assert adlar == ["ASSETS.json"]


# --- A4-24 / A4-25: kapı çöküşü ve sessiz atlama -------------------------------------- #


async def test_tek_kapinin_cokusu_butun_dogrulamayi_dusurmez():
    from fusion_cli.core.verification import VerificationResult
    from fusion_cli.engines.agent.verification import CompositeVerifier

    class Cokuyor:
        async def verify(self):
            raise RuntimeError("playwright patladı")

    class Temiz:
        async def verify(self):
            return VerificationResult(ok=False, summary="lint", findings=("lint kırık",))

    sonuc = await CompositeVerifier((Cokuyor(), Temiz())).verify()

    assert sonuc.ok is False
    assert sonuc.findings == ("lint kırık",)
    assert any("Cokuyor" in uyari and "DOĞRULANAMADI" in uyari for uyari in sonuc.warnings)


async def test_tarayici_denetimi_atlanirsa_neden_uyaridadir(tmp_path, monkeypatch):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent import site_verify

    class Bozuk:
        def __init__(self, context):
            pass

        async def observe_urls(self, adresler):
            raise RuntimeError("chromium yok")

    monkeypatch.setattr(site_verify, "BrowserVerifier", Bozuk)
    sonuc = SimpleNamespace(status=200, url="http://x/", links=())

    sonuc_ = await site_verify.SiteVerifier(ToolContext(root=tmp_path), None)._browser_audit(sonuc)

    assert sonuc_ is not None
    assert "atlandı" in sonuc_.warnings[0]


# --- A4-21 / A4-22 / A4-23: doğrulama komutu keşfi --------------------------------- #


def test_arac_yalniz_yorumda_ya_da_baska_paketin_adinda_geciyorsa_tanimli_sayilmaz(tmp_path):
    from fusion_cli.engines.agent.verify_discovery import discover_commands

    (tmp_path / "pyproject.toml").write_text(
        "# ruff sonra eklenecek\n[project]\nname='x'\ndependencies=['ruff-lsp']\n",
        encoding="utf-8",
    )

    assert discover_commands(tmp_path) == ()


def test_arac_yalniz_venvde_kuruluysa_venv_yolu_kullanilir(tmp_path):
    from fusion_cli.engines.agent.verify_discovery import discover_commands

    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\nline-length=100\n", encoding="utf-8")
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    (tmp_path / ".venv" / "bin" / "ruff").write_text("", encoding="utf-8")

    assert discover_commands(tmp_path) == (".venv/bin/ruff check .",)


def test_rust_ve_go_otomatik_kapisi_bos_kalmaz(tmp_path):
    from fusion_cli.engines.agent.verify_discovery import discover_auto_commands

    (tmp_path / "Cargo.toml").write_text("[package]\n", encoding="utf-8")
    assert discover_auto_commands(tmp_path) == ("cargo check",)
    (tmp_path / "Cargo.toml").unlink()
    (tmp_path / "go.mod").write_text("module x\n", encoding="utf-8")
    assert discover_auto_commands(tmp_path) == ("go vet ./...",)


def test_make_test_otomatik_kapidan_dislanir(tmp_path):
    from fusion_cli.engines.agent.verify_discovery import discover_auto_commands

    (tmp_path / "Makefile").write_text("test:\n\tpytest\n", encoding="utf-8")

    assert discover_auto_commands(tmp_path) == ()


@pytest.mark.parametrize(
    "komut",
    [
        "uv run pytest -q",
        "poetry run pytest tests/",
        "python -m unittest discover",
        "tox",
        "npx playwright test",
        "deno test",
        "mvn test",
        "./gradlew test",
        "dotnet test",
        "bundle exec rspec",
        "phpunit",
        "cargo +nightly test",
        "npm run test:unit",
    ],
)
def test_yaygin_test_kosuculari_davranis_kaniti_sayilir(komut):
    from fusion_cli.engines.agent.verify_discovery import is_behavioral_command

    assert is_behavioral_command(komut)


def test_bun_metin_kilit_dosyasi_taninir(tmp_path):
    from fusion_cli.engines.agent.verify_discovery import discover_commands

    (tmp_path / "package.json").write_text('{"scripts": {"test": "x"}}', encoding="utf-8")
    (tmp_path / "bun.lock").write_text("", encoding="utf-8")

    assert discover_commands(tmp_path) == ("bun run test",)


# --- A4-26 / A4-27 / A4-65: tur raporu ----------------------------------------------- #


def _yaz(yol):
    from fusion_cli.core.evidence import ToolUse

    return ToolUse(name="write_file", arguments={"path": yol}, ok=True, output="ok", mutating=True)


def _kabuk(komut, cikti):
    from fusion_cli.core.evidence import ToolUse

    return ToolUse(
        name="run_shell", arguments={"command": komut}, ok=True, output=cikti, mutating=True
    )


def test_cikis_kodu_okunamayan_komut_raporda_none_yazmaz_ve_basari_iddiasini_engeller():
    from fusion_cli.engines.agent.turn_report import build_turn_report

    rapor = build_turn_report(
        ("a.py",), (_yaz("a.py"), _kabuk("pytest -q", "zaman aşımı, çıktı kesildi")), gate=None
    )

    metin = rapor.render()
    assert "çıkış None" not in metin
    assert "zaman aşımı" in metin
    assert rapor.blocks_success is True


def test_kapsamli_degistirmedim_cumlesi_aciklamayi_gizlemez():
    from fusion_cli.engines.agent.turn_report import build_turn_report

    rapor = build_turn_report(
        ("a.py",), (_yaz("a.py"), _kabuk("pytest -q", "(çıkış kodu 0)\nok")), gate=None
    )

    metin = rapor.render_with_model_text(
        "src/ dışındaki dosyalarda değişiklik yapmadım; yalnız a.py'yi düzenledim."
    )
    assert "yalnız a.py'yi düzenledim" in metin
    tum = rapor.render_with_model_text("Hiçbir dosya değiştirmedim.")
    assert "açıklaması gösterilmedi" in tum


def test_cikis_kodu_oneki_uretici_ve_okuyucuda_ayni_sabittir():
    from fusion_cli.core.constants import EXIT_CODE_PREFIX
    from fusion_cli.engines.agent import turn_report

    assert turn_report._EXIT_CODE_PREFIX == EXIT_CODE_PREFIX


# --- A4-29 ... A4-33, A4-56: öğretmen akışı ------------------------------------------- #


def test_ogretmene_giden_kok_listesi_olasi_kimlik_dosyalarini_icermez(tmp_path):
    from fusion_cli.engines.agent.teacher_flow import _project_context

    for ad in (".env.local", "id_rsa", "anahtar.pem", "credentials.json", "app.py"):
        (tmp_path / ad).write_text("x", encoding="utf-8")

    baglam = _project_context(tmp_path, "görev")

    assert "app.py" in baglam
    for ad in (".env.local", "id_rsa", "anahtar.pem", "credentials.json"):
        assert ad not in baglam


def test_ogretmene_giden_fark_sir_dosyalarini_ve_buyuk_dosyalari_atlar(tmp_path):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent import teacher_flow

    baglam = ToolContext(root=tmp_path)
    sir = tmp_path / ".env.production"
    kod = tmp_path / "a.py"
    buyuk = tmp_path / "b.py"
    for yol, icerik in ((sir, "A=1\n"), (kod, "x = 1\n"), (buyuk, "y" * (600 * 1024))):
        baglam.changes.record_created(yol)
        yol.write_text(icerik, encoding="utf-8")
    deps = SimpleNamespace(tool_context=baglam)

    ozet = teacher_flow._diff_summary(deps)

    assert "a.py" in ozet
    assert ".env.production" not in ozet
    assert "b.py" not in ozet


def test_test_komutu_deseni_latest_ve_contest_e_takilmaz():
    from fusion_cli.engines.agent.teacher_flow import _TEST_COMMAND

    assert _TEST_COMMAND.search("pytest -q")
    assert _TEST_COMMAND.search("npm run build")
    assert _TEST_COMMAND.search("npm test")
    assert not _TEST_COMMAND.search("git checkout latest")
    assert not _TEST_COMMAND.search("cat contest.txt")


# --- A4-35 / A4-36 / A4-37: öğretmen ders, bütçe ve günlük ---------------------------- #


def test_ders_celiski_sezgisi_sozcuk_sinirina_bakar():
    from fusion_cli.engines.agent.teacher_lessons import _olasi_catisma

    # "yapmak" / "gözetmek" olumsuzlama değildir: iki ders aynı yönde.
    assert not _olasi_catisma("Testleri yapmak için pytest kullan", "Önce testleri yazmak gerekir")
    assert _olasi_catisma("Bu klasörde write_file kullanma", "write_file ile yaz")
    assert _olasi_catisma("Asla sudo çalıştırma", "sudo ile kur")


def test_butce_dosyasi_yazilamazsa_arac_cokmez(tmp_path):
    # Bütçe klasörü yerine DOSYA koy: mkdir/yazma OSError verir.
    from fusion_cli.engines.agent.teacher_budget import budget_file, check_and_spend

    klasor = budget_file(tmp_path).parent
    klasor.parent.mkdir(parents=True, exist_ok=True)
    klasor.write_text("dosya", encoding="utf-8")

    kontrol = check_and_spend(tmp_path, now=1000.0)

    assert kontrol.allowed is True


def test_butce_sayaci_atomik_yazilir_ve_gecici_dosya_birakmaz(tmp_path):
    from fusion_cli.engines.agent.teacher_budget import budget_file, check_and_spend

    check_and_spend(tmp_path, now=1000.0)
    check_and_spend(tmp_path, now=1001.0)

    klasor = budget_file(tmp_path).parent
    assert [p.name for p in klasor.iterdir()] == [budget_file(tmp_path).name]


def test_ogretmen_gunlugu_ekleme_kipinde_maskeler_ve_bozuk_utf8de_cokmez(tmp_path):
    from fusion_cli.engines.agent.teacher_notebook import NOTEBOOK_PATH, append_entry

    yol = tmp_path / NOTEBOOK_PATH
    yol.parent.mkdir(parents=True)
    yol.write_bytes("# Öğretmen günlüğü\n".encode() + b"\xff\xfe bozuk bayt\n")

    append_entry(
        tmp_path,
        timestamp="t1",
        question="soru",
        answer="anahtar ghp_" + "a" * 36,
        lesson_written=False,
    )

    metin = yol.read_text(encoding="utf-8", errors="replace")
    assert "bozuk bayt" in metin
    assert "ghp_" + "a" * 36 not in metin
    assert "## t1" in metin


async def test_hafiza_plan_aramasi_olay_dongusunu_bloklamaz(monkeypatch):
    import threading

    from fusion_cli.engines.agent import teacher_flow

    ana_is_parcacigi = threading.get_ident()
    calisan: list[int] = []

    def bul(*args, **kwargs):
        calisan.append(threading.get_ident())

    monkeypatch.setattr(teacher_flow, "find_reusable_plan", bul)
    monkeypatch.setattr(
        "fusion_cli.engines.agent.learning_steps._workspace", lambda deps: "w", raising=True
    )
    monkeypatch.setattr(
        "fusion_cli.engines.agent.learning_steps.lesson_tags", lambda deps: (), raising=True
    )
    deps = SimpleNamespace(
        lessons=object(),
        config=make_config(runtime={"lessons": True}),
        lesson_context=LessonRuntimeContext(),
    )

    assert await teacher_flow._apply_remembered_plan("görev", [], deps) is False
    assert calisan and calisan[0] != ana_is_parcacigi


def test_gorev_kokleri_buyuk_noktali_i_yi_bolmez():
    from fusion_cli.engines.agent.teacher_memory import _stems

    assert _stems("İstanbul şubesi raporu") == _stems("istanbul şubesi raporu")


# --- A4-39 / A4-40 / A4-41: ekip (team) --------------------------------------------- #


async def test_gecersiz_yazma_alani_modele_duzeltilebilir_hata_olarak_doner(tmp_path):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
    from fusion_cli.engines.agent.loop import AgentDeps
    from fusion_cli.engines.agent.team import spawn_agents_tool
    from fusion_cli.tools.capabilities import CapabilityRegistry
    from tests.agent_harness import Publisher
    from tests.fakes import AlwaysApprove, RecordingSink, make_config

    deps = AgentDeps(
        config=make_config(),
        publisher=Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path, write_scope=(tmp_path / "izinli",)),
        capabilities=CapabilityRegistry(tmp_path / "ev", tmp_path),
    )

    async def ajan(*_a, **_k):
        raise AssertionError("alan geçersizken ajan başlamamalı")

    arac = spawn_agents_tool(deps, depth=0, run_agent=ajan)
    sonuc = await arac.run(
        {"gorevler": [{"task": "a", "yazma_alani": ["baska/dosya.txt"]}]}, deps.tool_context
    )

    assert sonuc.ok is False
    assert "yazma alanı" in sonuc.output.lower()


def test_uye_raporu_baglami_sisirmez():
    from fusion_cli.engines.agent.team_policy import MEMBER_REPORT_CHARS, cap_report

    uzun = "x" * (MEMBER_REPORT_CHARS * 3)

    assert len(cap_report(uzun)) < MEMBER_REPORT_CHARS + 100
    assert "kırpıldı" in cap_report(uzun)
    assert cap_report("kısa") == "kısa"


# --- A4-42 / A4-43 / A4-49 ------------------------------------------------------------ #


def test_belirsiz_goster_calistir_istekleri_web_baglami_olmadan_onizleme_sayilmaz():
    from fusion_cli.engines.agent.turn_hints import PREVIEW_NOTE, preview_hint

    assert preview_hint("kodu göster", available=True) is None
    assert preview_hint("testleri çalıştır", available=True) is None
    assert preview_hint("siteyi göster", available=True) == PREVIEW_NOTE
    assert preview_hint("sayfayı çalıştır", available=True) == PREVIEW_NOTE


def test_webkit_keyframes_ve_sekmeli_gecis_yakalanir():
    from fusion_cli.engines.agent.web_motion import layout_animations

    assert layout_animations(".a{transition:\tleft 1s}")
    # Boyut geçişi artık engel değil uyarı (A4-43).
    assert layout_animations(".a{transition:\twidth 1s}") == []
    assert layout_animations("@-webkit-keyframes k{from{left:0}to{left:9px}}")
    assert layout_animations(".a{transition: opacity 1s}") == []


def test_aday_toplama_once_butun_kardesleri_sonra_cocuklari_alar(tmp_path):
    from fusion_cli.engines.agent.workspace_hint import MAX_CANDIDATES, _candidates

    kok = tmp_path / "burasi"
    kok.mkdir()
    for i in range(MAX_CANDIDATES - 5):
        (tmp_path / f"a{i:03}" / "cocuk").mkdir(parents=True)
    (tmp_path / "zzz-dogru-proje").mkdir()

    adaylar = [p.name for p in _candidates(kok)]

    assert "zzz-dogru-proje" in adaylar


# --- A4-44 / A4-45 / A4-64: web_verify ------------------------------------------------- #


def test_bos_baglanti_yalniz_gercek_etiketlerde_ve_mesru_olmayanlarda_sayilir():
    from fusion_cli.engines.agent.web_verify import _bos_baglantilar

    meshru = (
        '<a href="#" role="button" id="menu">Menü</a>'
        '<a href="#" onclick="ac()">Aç</a>'
        '<a href="#" aria-controls="x">x</a>'
        '<!-- <a href="#">yorum</a> -->'
        "<script>const s = '<a href=\"#\">';</script>"
    )
    assert _bos_baglantilar(meshru) == []
    assert _bos_baglantilar("<a href='#'>boş</a><a href=\"#\">boş</a>")[0].startswith("2 boş")


def test_img_kaynagi_tek_tirnakliysa_olu_servis_yakalanir():
    from fusion_cli.engines.agent.web_verify import _olu_gorseller

    assert _olu_gorseller("<img src='https://via.placeholder.com/10'>")


def test_hp_takma_ad_ve_hasar_fonksiyonu_azaltma_sayilir():
    from fusion_cli.engines.agent.web_verify import _erisilemez_hp_dali

    takma_ad = "if (state.player.hp <= 0) end();\nconst p = state.player;\np.hp -= 1;"
    fonksiyon = "if (player.hp <= 0) end();\nfunction f(){ takeDamage(player, 3); }"
    gercek_eksik = "if (enemy.hp <= 0) win();"

    assert _erisilemez_hp_dali(takma_ad) == []
    assert _erisilemez_hp_dali(fonksiyon) == []
    assert _erisilemez_hp_dali(gercek_eksik)


def test_html_yorumundaki_kapanmayan_script_bulgu_uretmez():
    from fusion_cli.engines.agent.web_verify import _kapanmayan_ham_metin_etiketleri

    assert _kapanmayan_ham_metin_etiketleri("<!-- <script> örnek --><p>x</p>") == []
    assert _kapanmayan_ham_metin_etiketleri("<script>var a;")


# --- A4-46 / A4-47 / A4-48 / A4-63 ---------------------------------------------------- #


def test_gorme_modeli_dusunce_blogundan_sonraki_karari_okur():
    from fusion_cli.engines.agent.visual_verify import parse_verdict

    assert parse_verdict("<think>belki hayır der</think>EVET, çok boşluk var")
    assert not parse_verdict("<think>evet gibi</think>HAYIR")


async def test_site_design_ek_sayfa_ic_ag_adresini_reddeder(tmp_path):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.web_tools import run_site_design

    sonuc = await run_site_design(
        {"url": "http://93.184.216.34", "pages": ["http://169.254.169.254/latest/meta-data"]},
        ToolContext(root=tmp_path),
    )

    assert sonuc.ok is False
    assert "169.254.169.254" in sonuc.output


async def test_play_probe_beklenmeyen_hata_modele_neden_olarak_doner(tmp_path, monkeypatch):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent import web_tools
    from fusion_cli.tools import play_probe

    async def bozuk(*_a, **_k):
        raise RuntimeError("Executable doesn't exist")

    monkeypatch.setattr(play_probe, "probe_game", bozuk)

    sonuc = await web_tools.run_play_probe(
        {"target": "http://127.0.0.1:1/"}, ToolContext(root=tmp_path)
    )

    assert sonuc.ok is False
    assert "Executable" in sonuc.output


async def test_gorsel_denetim_atlanirsa_uyari_verir(tmp_path, monkeypatch):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.visual_verify import VisualVerifier

    sayfa = tmp_path / "index.html"
    sayfa.write_text("<html></html>", encoding="utf-8")
    baglam = ToolContext(root=tmp_path)
    baglam.touched.add(sayfa)
    kurucu = VisualVerifier(baglam, SimpleNamespace(vision=object()))

    async def patla(_yol):
        raise RuntimeError("chromium yok")

    monkeypatch.setattr(kurucu, "_inspect", patla)

    sonuc = await kurucu.verify()

    assert sonuc.ok is True
    assert "atlandı" in sonuc.warnings[0]


# --- A4-50 / A4-51 / A4-52: review ----------------------------------------------------- #


@pytest.mark.parametrize(
    ("cevap", "temiz"),
    [
        ("TAMAM", True),
        ("TAMAM, her şey yolunda.", True),
        ("TAMAM. Hata yok, eksiksiz.", True),
        ("TAMAM DEĞİL: testler hiç çalıştırılmadı", False),
        ("Tamam, ama sepet rotası eksik", False),
        ("Sorun yok, görev eksiksiz.", True),
        ("Bir sorun bulamadım.", True),
        ("write_file ile index.html yazılmadı; dosyayı oluştur", False),
    ],
)
def test_denetci_karari_itirazli_tamami_temiz_saymaz(cevap, temiz):
    from fusion_cli.engines.agent import review

    assert (review.parse_feedback(cevap) == "") is temiz


async def test_denetim_istemi_iz_icindeki_yer_tutucuyu_yeniden_doldurmaz(monkeypatch):
    from fusion_cli.core.types import Message, ModelResult
    from fusion_cli.engines.agent import review

    istemler: list[str] = []

    async def sor(prompt, config, publisher):
        istemler.append(prompt)
        return ModelResult(text="TAMAM", ok=True)

    monkeypatch.setattr(review, "_ask", sor)
    config = make_config(runtime={"judge_timeout_s": 5.0})

    await review.review_turn(
        "görev {final}", "SON-METIN", [Message("user", "iz {task}")], config=config
    )

    assert "görev {final}" in istemler[0]
    assert "iz {task}" in istemler[0]


# --- A4-55 / A4-58 -------------------------------------------------------------------- #


def test_brief_kirpma_notu_gercek_siniri_soyler():
    from fusion_cli.engines.agent.teacher_brief import compile_brief

    brief = compile_brief(
        durum="d" * 5000, denenenler="", question="soru?", char_budget=1000, frame=""
    )

    assert brief.truncated
    assert "1.000 karakter" in brief.text
    assert "25.000" not in brief.text
    assert len(brief.text) <= 1000


def test_gecici_hata_yalin_502_sayisina_takilmaz():
    from fusion_cli.engines.agent.transient import is_transient_failure

    assert not is_transient_failure("dosya.py satır 503'te sözdizimi hatası, fiyat 504 TL")
    assert is_transient_failure("HTTP 503 Service Unavailable")
    assert is_transient_failure("status code 502")
