"""Geliştirme isteği "salt okuma" sanılmamalı.

Ölçüldü (29 Eylül): "projesini tam anlamıyla geliştir ... her şeyi oku ne işe
yaradığını anla ... ayarla ... UI'a sahip olsun istiyorum ... bir fonksiyon daha
istiyorum" görevi yalnız "proje ... oku" kalıbına uyduğu için `workspace_read`
sayıldı; yazma araçları kapatıldı, model dört koşu boyunca tek dosya yazamadı.
"""

from __future__ import annotations

import pytest

from fusion_cli.engines.agent.loop import run_agent
from fusion_cli.engines.agent.tool_constraints import forbidden_families, prohibited_tool
from fusion_cli.engines.effects.detect import required_effect_for

from .agent_harness import install_provider, web_deps
from .fakes import RecordingSink, ScriptedProvider, model_result, tool_call

MUTASYON = "workspace_mutation"

GAME_PAUSE_REPAIR_TASK = (
    "Bu klasördeki index.html blok yakalama oyununda, oyun oynanırken görünen ve etkin bir "
    "Duraklat düğmesi ekle. Bu düğme oyunu dondursun. Duraklatılmışken görünen Devam Et "
    "düğmesi, skoru, kalan canları, oyuncu konumunu ve mevcut düşen blokları sıfırlamadan "
    "aynı oyunu sürdürsün. Başlat, yeniden başlat, klavye ve dokunmatik kontrolleri, skor ve "
    "üç can döngüsünü, Türkçe arayüzü ve mobil uyumu koru. Yalnızca index.html dosyasını "
    "değiştir. Harici bağımlılık ekleme, shell komutu çalıştırma, sunucu başlatma, uygulama "
    "veya tarayıcı açma. Sonucu kısa yaz."
)


def test_game_pause_repair_preserves_start_controls_with_shell_forbidden():
    denied = forbidden_families(GAME_PAUSE_REPAIR_TASK)
    assert prohibited_tool("run_shell", denied)
    assert prohibited_tool("browser_open", denied)
    assert required_effect_for(GAME_PAUSE_REPAIR_TASK) == MUTASYON


@pytest.mark.parametrize("with_edit", [True, False], ids=["edited", "missing-edit"])
async def test_game_pause_repair_closes_only_with_file_mutation(monkeypatch, tmp_path, with_edit):
    page = tmp_path / "index.html"
    original = '<button id="start">Başlat</button>\n'
    edited = original + '<button id="pause">Duraklat</button>\n'
    page.write_text(original, encoding="utf-8")
    reply = model_result("Duraklat düğmesini index.html dosyasına ekledim.")
    edit = tool_call("edit_file", path="index.html", old=original, new=edited)
    script = [model_result(tool_calls=(edit,)), reply] if with_edit else [reply] * 4
    install_provider(monkeypatch, ScriptedProvider(script))

    outcome = await run_agent(
        GAME_PAUSE_REPAIR_TASK,
        web_deps(tmp_path, RecordingSink()),
        allowed_tools={"read_file", "write_file", "edit_file", "list_dir", "search_code"},
        verify=False,
        self_review=False,
    )

    assert page.read_text(encoding="utf-8") == (edited if with_edit else original)
    assert outcome.mutating_tool_calls_made == int(with_edit)
    assert outcome.ok is with_edit, outcome.final_text


@pytest.mark.parametrize(
    "preservation",
    [
        "Başlat, Yeniden Başlat, klavye kontrollerini koru.",
        "Başlat ve Yeniden Başlat düğmelerini koru.",
    ],
)
def test_preserved_start_control_labels_do_not_require_shell_without_a_prohibition(preservation):
    assert required_effect_for(f"index.html dosyasını değiştir. {preservation}") == MUTASYON


@pytest.mark.parametrize(
    "task",
    [
        "Başlat, yeniden başlat.",
        "Sunucuyu başlat, yeniden başlat, klavye kontrollerini koru.",
        "Başlat. Yeniden başlat, klavye kontrollerini koru.",
        "Başlat, yeniden başlat, klavye kontrollerini ayarla, verileri koru.",
        (
            "Başlat, yeniden başlat, klavye kontrollerini koru. "
            "index.html dosyasını değiştir ve test sunucusunu yeniden başlat."
        ),
        "Prod sunucusunu başlatma ama yerel test sunucusunu başlat.",
    ],
)
def test_explicit_shell_commands_keep_shell_completion_requirement(task):
    assert required_effect_for(task) == "shell_action"


def test_shell_prohibition_does_not_erase_contradictory_shell_request():
    task = "Shell kullanma. index.html dosyasını değiştir ve test sunucusunu yeniden başlat."

    assert prohibited_tool("run_shell", forbidden_families(task))
    assert required_effect_for(task) == "shell_action"


@pytest.mark.parametrize(
    "gorev",
    [
        (
            "ornek proje projesini tam anlamıyla geliştir çok profesyonel bir hale gelmiş "
            "olsun bu projedeki her işi her şeyi oku ne işe yaradığını anla"
        ),
        "mcp sunucusu falan ne ayarlaman lazımsa ayarla",
        "görünüm olarak da APPLE benzeri bir UI a sahip olsun istiyorum",
        "örnek olarak bir fonksiyon daha istiyorum otomatik story",
        "giriş sayfasını iyileştir",
        "bu özelliği projeye uygula",
    ],
)
def test_gelistirme_istegi_degisiklik_sayilir(gorev):
    assert required_effect_for(gorev) == MUTASYON


@pytest.mark.parametrize(
    ("gorev", "beklenen"),
    [
        ("projedeki dosyaları oku ve listele", "workspace_read"),
        ("merhaba nasılsın", None),
    ],
)
def test_salt_okuma_ve_sohbet_etkilenmez(gorev, beklenen):
    assert required_effect_for(gorev) == beklenen


@pytest.mark.parametrize(
    "gorev",
    [
        "uygulamanın ayarlarını göster",
        "geliştirme ortamı nedir",
        "bu uygulama ne işe yarıyor",
    ],
)
def test_isim_olarak_gecen_fiil_kokleri_degisiklik_sayilmaz(gorev):
    assert required_effect_for(gorev) != MUTASYON


# --- E1-07: isim olan sözcükler olumsuzlama sayılmaz -------------------------------------


@pytest.mark.parametrize(
    "gorev",
    [
        "Arama kutusu ekle",
        "yükleme ekranı oluştur",
        "araştırma sayfası yaz",
        "Hero bölümüne arama kutusu ekle, edit_file kullan",
        "a.py dosyası oluştur ama silme lütfen",
    ],
)
def test_isim_olarak_gecen_sozcuk_mutasyon_kapisini_kapatmaz(gorev):
    from fusion_cli.engines.effects.detect import required_effect_for

    assert required_effect_for(gorev) is not None


@pytest.mark.parametrize(
    "gorev",
    ["dosyayı silme", "a.py dosyası oluşturma", "Dosya oluşturma lütfen", "lütfen yapma"],
)
def test_fiil_kipindeki_olumsuz_emir_mutasyon_istemez(gorev):
    from fusion_cli.engines.effects.detect import required_effect_for

    assert required_effect_for(gorev) is None


# --- Dalga 4: büyük harfli Türkçe girdi kalıpları bozmaz (E1-12) ----------------- #


def test_buyuk_harfli_turkce_gorev_mutasyon_sayilir():
    """Ölçüldü (30 Ekim): 'DOSYAYI SİL' → `İ`.lower() iki karakter olduğundan None dönüyordu."""
    from fusion_cli.engines.effects.detect import required_effect_for
    from fusion_cli.engines.effects.model import EffectKind  # noqa: F401

    assert required_effect_for("DOSYAYI SİL") == required_effect_for("dosyayı sil")
    assert required_effect_for("DÜZELT İNDEX.HTML") == required_effect_for("düzelt index.html")
    assert required_effect_for("DOSYAYI SİL") is not None


def test_buyuk_harfli_ingilizce_gorev_bozulmaz():
    from fusion_cli.engines.effects.detect import required_effect_for

    assert required_effect_for("FIX THE BUG IN app.py") == required_effect_for(
        "fix the bug in app.py"
    )


def test_ortak_kucultme_dotted_i_yi_tek_karaktere_indirir():
    from fusion_cli.core.text_fold import lower_tr_aware

    assert lower_tr_aware("SİL") == "sil"
    assert lower_tr_aware("İSTEK") == "istek"
    assert lower_tr_aware("INDEX") == "index"
    assert lower_tr_aware("kız") == "kız"


# --- Dalga 4: salt okuma cümleleri mutasyon / commit sayılmaz (E1-44) ------------- #


def test_isim_halindeki_fiil_koku_mutasyon_sayilmaz():
    """Ölçüldü (30 Ekim): 'son güncellemeleri listele' workspace_mutation çıkıyordu."""
    from fusion_cli.engines.effects.detect import required_effect_for

    for gorev in (
        "son güncellemeleri listele",
        "ekleme tarihini göster",
        "silinen dosyaları listele",
    ):
        assert required_effect_for(gorev) != "workspace_mutation", gorev


def test_emir_ve_rica_kipleri_mutasyon_kalir():
    from fusion_cli.engines.effects.detect import required_effect_for

    for gorev in ("kodu güncelle", "bunu düzeltin", "şunu ekleyelim", "hatayı düzeltsene", "sil"):
        assert required_effect_for(gorev) == "workspace_mutation", gorev


def test_commitment_ve_commitleri_goster_git_commit_sayilmaz():
    from fusion_cli.engines.effects.detect import required_effect_for

    for gorev in ("committee üyelerini say", "son commitleri göster", "commitment kavramı"):
        assert required_effect_for(gorev) != "git_commit", gorev
    assert required_effect_for("değişiklikleri commitle") == "git_commit"
