"""30 Eylül "WordPress tabanlı site" sohbetindeki sorunların gerileme testleri.

Kök neden raporu: docs/superpowers/plans/2026-10-02-wordpress-sohbeti-kok-neden.md
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest

from fusion_cli.core.events import ToolExecuted, ToolOutcome
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.types import CompletionRequest, ModelResult, StreamDone, TextChunk
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent.approval import (
    ApprovalMode,
    AutoApproval,
    Decision,
    build_policy,
    build_request,
)
from fusion_cli.engines.agent.history_tools import recent_actions_tool
from fusion_cli.engines.agent.loop import AgentDeps, run_agent
from fusion_cli.engines.agent.php_verify import PhpVerifier, find_php_executable
from fusion_cli.engines.agent.project_instructions import container_root_note
from fusion_cli.engines.agent.turn_report import UNVERIFIED_CLAIM_WARNING, build_turn_report
from fusion_cli.engines.effects.detect import is_history_question, required_effect_for
from fusion_cli.observability.audit import AuditSink
from fusion_cli.tools import shell
from fusion_cli.tools.builtin import build_registry
from fusion_cli.tools.delete_preview import describe_delete, script_danger
from fusion_cli.tools.files import read_file
from tests.agent_harness import Publisher, install_provider
from tests.fakes import (
    AlwaysApprove,
    RecordingSink,
    ScriptedProvider,
    make_config,
    model_result,
    tool_call,
)


@pytest.fixture
def masaustu(tmp_path) -> Path:
    """Olaydaki düzen: Masaüstü kökünde birden çok proje."""
    desktop = tmp_path / "ev" / "Desktop"
    for proje in ("01-Projeler/fusion-cli", "01-Projeler/projeler/GATE HOLDING", "sneaksup-wp"):
        (desktop / proje / ".git").mkdir(parents=True)
    return desktop


# A — betik yoluyla silme artık sorulur


def test_silen_python_betigi_tehlikeli_sayilir(tmp_path):
    (tmp_path / "temizle.py").write_text(
        "import shutil\nshutil.rmtree('/Users/x/Desktop')\n", encoding="utf-8"
    )
    (tmp_path / "rapor.py").write_text("print('merhaba')\n", encoding="utf-8")

    assert "rmtree" in (script_danger("python3 temizle.py", tmp_path) or "")
    assert script_danger("python3 rapor.py", tmp_path) is None


@pytest.mark.parametrize(
    ("betik", "icerik"),
    [
        ("sil.sh", "rm -rf ../*\n"),
        ("sil.js", "require('fs').rmSync(require('os').homedir() + '/x', {recursive: true})\n"),
        ("sil.php", "<?php unlink('/Users/x/a.txt');\n"),
    ],
)
def test_proje_disina_silen_betikler_her_dilde_yakalanir(tmp_path, betik, icerik):
    (tmp_path / betik).write_text(icerik, encoding="utf-8")
    calistirici = {"sh": "bash", "js": "node", "php": "php"}[betik.split(".")[1]]

    assert script_danger(f"{calistirici} {betik}", tmp_path) is not None


def test_projenin_kendi_temizlik_betigi_sorulmaz(tmp_path):
    """Kullanıcı (2 Ekim): gereksiz soru sorma. `dist`'i silen proje betiği olağandır."""
    (tmp_path / "temizle.py").write_text("import shutil\nshutil.rmtree('dist')\n", encoding="utf-8")

    assert script_danger("python3 temizle.py", tmp_path) is None


def test_proje_deposunda_silen_betik_her_zaman_sorulur(masaustu):
    (masaustu / "temizle.py").write_text("import shutil\nshutil.rmtree('dist')\n", encoding="utf-8")

    assert "birden çok proje" in (script_danger("python3 temizle.py", masaustu) or "")


async def test_otomatik_kip_silen_betigi_sormadan_calistirmaz(tmp_path):
    (tmp_path / "sil.py").write_text(
        "import os\nos.remove(os.path.expanduser('~/a'))\n", encoding="utf-8"
    )
    sorulan: list[object] = []

    class _Kayit:
        async def confirm(self, request):
            sorulan.append(request)
            return False

    istek = build_request(
        build_registry().get("run_shell"), {"command": "python3 sil.py"}, root=tmp_path
    )
    karar = await AutoApproval(_Kayit()).decide(istek)

    assert sorulan and karar is not Decision.ALLOW
    assert "geri alınamaz" in (istek.danger or "")


# B — onay kartı hedefi tam yolu, boyutu ve akıbetiyle gösterir


def test_silme_karti_tam_yol_ve_akibet_gosterir(masaustu):
    metin = describe_delete("rm -rf sneaksup-wp", masaustu, masaustu.parent)

    assert str(masaustu / "sneaksup-wp") in metin
    assert "öğe" in metin and "çöpüne taşınır" in metin


def test_olaydaki_komut_kartta_dikkat_diye_gorunur(masaustu):
    metin = describe_delete("rm -rf 01-Projeler", masaustu, masaustu.parent)

    assert "DİKKAT" in metin and "birden çok proje" in metin


# C — kök bir proje deposuysa model bilir


def test_masaustu_koku_proje_deposu_uyarisi_alir(masaustu):
    notu = container_root_note(masaustu, masaustu.parent)

    assert "PROJE DEPOSU" in notu
    assert "sneaksup-wp" in notu and "01-Projeler/fusion-cli" in notu


def test_tek_proje_kokunde_uyari_yok(masaustu):
    assert container_root_note(masaustu / "sneaksup-wp", masaustu.parent) == ""


# D — geçmiş sorusu iş emri sayılmaz


@pytest.mark.parametrize(
    "mesaj",
    [
        "hatalı bir şey silmiş olabilir misin?",
        "neyi sildin?",
        "ne yaptın?",
        "header.php'yi düzelttin mi?",
    ],
)
def test_gecmis_sorusu_salt_okuma(mesaj):
    assert is_history_question(mesaj)
    assert required_effect_for(mesaj) == "workspace_read"


@pytest.mark.parametrize(
    "mesaj",
    ["projeyi tamamiyle sil", "dosyaları düzeltir misin?", "dosyayı sildin, geri al"],
)
def test_is_istegi_salt_okumaya_dusmez(mesaj):
    assert required_effect_for(mesaj) == "workspace_mutation"


async def test_gecmis_sorusunda_ajan_dosya_yazamaz(tmp_path, monkeypatch):
    install_provider(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("write_file", path="style.css", content="x")]),
                model_result("Hayır, bu turda hiçbir şey silmedim."),
            ]
        ),
    )
    deps = AgentDeps(
        config=make_config(),
        publisher=Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )

    await run_agent("hatalı bir şey silmiş olabilir misin?", deps)

    assert not (tmp_path / "style.css").exists()


def test_recent_actions_gercek_arac_kaydini_okur(tmp_path):
    sink = AuditSink(tmp_path / "audit", "sohbet-1", root=tmp_path)
    sink.handle(
        ToolExecuted(
            name="run_shell", args={"command": "rm -rf eski"}, outcome=ToolOutcome.OK, output=""
        )
    )
    arac = recent_actions_tool(tmp_path, "sohbet-1")

    sonuc = arac.run({}, ToolContext(root=tmp_path))

    assert "run_shell" in sonuc.output and "rm -rf eski" in sonuc.output
    assert not arac.mutating


# E — uydurma yol çalıştırılmaz


def test_uydurma_yollu_kabuk_komutu_calismaz(tmp_path):
    sonuc = shell.run_shell(
        {"command": "ls /Users/mnt/data/Users/motogate/Desktop/sneaksup-wp"},
        ToolContext(root=tmp_path),
    )

    assert not sonuc.ok and "bu bilgisayarda YOK" in sonuc.output and str(tmp_path) in sonuc.output


def test_uydurma_yollu_dosya_okuma_anlasilir_hata_verir(tmp_path):
    from fusion_cli.core.errors import PathAccessError

    with pytest.raises(PathAccessError, match="bu bilgisayarda YOK"):
        read_file({"path": "/mnt/data/tema/style.css"}, ToolContext(root=tmp_path))


# F — PHP ve WordPress teması doğrulanır


def _tema(tmp_path: Path) -> Path:
    tema = tmp_path / "wp-content" / "themes" / "deneme"
    (tema / "template-parts").mkdir(parents=True)
    (tema / "style.css").write_text("/*\nTheme Name: Deneme\n*/", encoding="utf-8")
    (tema / "template-parts" / "content.php").write_text("<?php echo 1;", encoding="utf-8")
    return tema


def _dogrula(tmp_path: Path, tema: Path, php: str | None):
    baglam = ToolContext(root=tmp_path)
    baglam.touched.update(tema.rglob("*.php"))
    return asyncio.run(PhpVerifier(baglam, php).verify())


def test_temada_olmayan_dosyaya_baslanti_engellenir(tmp_path):
    tema = _tema(tmp_path)
    (tema / "functions.php").write_text(
        "<?php\n"
        "wp_enqueue_script('nav', get_template_directory_uri() . '/js/navigation.js');\n"
        "// wp_enqueue_style('x', get_template_directory_uri() . '/yorumda.css');\n"
        "load_theme_textdomain('d', get_template_directory() . '/languages');\n"
        "get_template_part('template-parts/content', 'yok');\n"
        "get_template_part('template-parts/olmayan');\n"
        "wc_get_template_part('content', 'product');\n",
        encoding="utf-8",
    )

    sonuc = _dogrula(tmp_path, tema, None)

    bulgular = "\n".join(sonuc.findings)
    assert not sonuc.ok
    assert "js/navigation.js" in bulgular
    assert "template-parts/olmayan" in bulgular
    # content-yok.php yok ama content.php'ye düşer; yorum, klasör ve WooCommerce sayılmaz.
    assert "content-yok" not in bulgular
    assert "yorumda.css" not in bulgular and "languages" not in bulgular
    assert "content-product" not in bulgular
    assert sonuc.warnings  # PHP verilmedi: "doğrulanamadı" uyarısı


@pytest.mark.skipif(find_php_executable() is None, reason="PHP kurulu değil")
def test_php_sozdizimi_hatasi_engellenir_temiz_dosya_kanit_uretir(tmp_path):
    tema = _tema(tmp_path)
    (tema / "front-page.php").write_text("<?php echo esc_url( 'a' : 'b' );", encoding="utf-8")

    hatali = _dogrula(tmp_path, tema, find_php_executable())
    (tema / "front-page.php").write_text("<?php echo 'tamam';", encoding="utf-8")
    temiz = _dogrula(tmp_path, tema, find_php_executable())

    assert not hatali.ok and "sözdizimi hatası" in hatali.findings[0]
    assert temiz.ok and temiz.evidence and "php -l" in temiz.evidence[0].summary


# G — kanıtsız "doğrulandı" iddiası geçersiz sayılır


def test_kanitsiz_dogrulama_iddiasi_uyarilir_ve_turu_basarisiz_yapar():
    rapor = build_turn_report(("tema/functions.php",), (), None)
    metin = "Tema dosyaları tamamlandı ve doğrulandı. Tüm PHP dosyaları hatasız."

    from dataclasses import replace

    isaretli = replace(rapor, false_claim=True)

    assert UNVERIFIED_CLAIM_WARNING in rapor.render_with_model_text(metin)
    assert isaretli.blocks_success
    assert UNVERIFIED_CLAIM_WARNING not in rapor.render_with_model_text("Dosyaları yazdım.")


# H — düşünme bütçeyi yerse bütçe büyütülür


async def test_dusunme_butceyi_yerse_butce_buyutulup_yeniden_denenir(tmp_path, monkeypatch):
    istenen: list[int] = []

    class _Saglayici:
        label = "sahte"

        async def complete(self, request):
            raise AssertionError("akış bekleniyordu")

        async def stream(self, request: CompletionRequest):
            istenen.append(request.max_tokens)
            if len(istenen) == 1:
                yield StreamDone(
                    ModelResult(
                        name="agent",
                        model="sahte",
                        text="",
                        latency_ms=1,
                        ok=False,
                        error="Model çıktı bütçesi dolduğu için cevabı üretemedi",
                        truncated=True,
                    )
                )
                return
            yield TextChunk("cevap")
            yield StreamDone(
                ModelResult(name="agent", model="sahte", text="cevap", latency_ms=1, ok=True)
            )

    install_provider(monkeypatch, _Saglayici())
    deps = AgentDeps(
        config=make_config(),
        publisher=Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )

    sonuc = await run_agent("merhaba de", deps)

    assert "cevap" in sonuc.final_text
    assert istenen[1] == istenen[0] * 2


def test_olay_komutlari_onay_kartinda_json_ile_tasinabilir():
    # Kart metni tel üzerinden gider: JSON'a çevrilebilir kalmalı.
    assert json.dumps({"tehlike": describe_delete("rm -rf x", Path("/tmp"), Path("/tmp"))})
    assert shutil.which("python3")
    assert agent_loop.MAX_TOKENS_ESCALATION >= 2


# Uçtan uca: olayı gerçek döngüyle, KÖR ONAYLA canlandır


async def test_olay_otomatik_kip_sorar_onaylanan_silme_cope_gider_ve_geri_alinir(
    masaustu, monkeypatch, tmp_path
):
    """Olay gecesinin komutu: kullanıcı silmek isterse siler, ama ne silindiğini görür
    ve her şey geri alınabilir kalır (2 Ekim: kesin ret kaldırıldı)."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: masaustu.parent))
    monkeypatch.setattr(shell, "trash_dir", lambda: tmp_path / "cop")
    for proje in ("01-Projeler/projeler/GATE HOLDING", "sneaksup-wp"):
        (masaustu / proje / "dosya.txt").write_text("değerli", encoding="utf-8")
    install_provider(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("run_shell", command="rm -rf ./*")]),
                model_result("Proje silindi."),
            ]
        ),
    )
    sorulan: list[object] = []

    class _Evet:
        async def confirm(self, request):
            sorulan.append(request)
            return True

    deps = AgentDeps(
        config=make_config(runtime={"self_review": False}),
        publisher=Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.AUTO, _Evet()),
        tool_context=ToolContext(root=masaustu),
    )

    await run_agent("projeyi tamamiyle sil ben sıfırdan oluşturacağım", deps)

    # Otomatik kip bile sordu ve kart proje deposunu söyledi.
    assert len(sorulan) == 1
    assert "birden çok proje" in (sorulan[0].note or "")
    # Silinen her şey Fusion çöpünde; geri alınınca değerli dosyalar yerinde.
    from fusion_cli.tools.safe_delete import list_trash, restore

    girdiler = list_trash(tmp_path / "cop")
    assert {g.original.name for g in girdiler} == {"01-Projeler", "sneaksup-wp"}
    for girdi in girdiler:
        restore(tmp_path / "cop", girdi.id)
    assert (masaustu / "01-Projeler/projeler/GATE HOLDING/dosya.txt").exists()
    assert (masaustu / "sneaksup-wp/dosya.txt").exists()
