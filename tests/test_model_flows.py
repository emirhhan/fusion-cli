"""`/level` ve `/development` akışları — seçim, uygulama ve kalıcılaştırma.

Seçim ekranı ve katalog enjekte edilir: gerçek terminal ve ağ olmadan test edilir.
"""

from __future__ import annotations

import pytest

from fusion_cli.cli.repl import model_flows
from fusion_cli.cli.repl.commands import RENDERED_COMMANDS, build_registry, parse
from fusion_cli.config.loader import load_config
from fusion_cli.config.model_select import SINGLE_MODEL_NAME
from fusion_cli.providers.catalog import CatalogEntry
from fusion_cli.ui import messages


@pytest.fixture
def config(tmp_path, monkeypatch):
    """Yazımın kullanıcı dizinine değil `tmp_path`'e gitmesi için kaynak ayarlanır."""
    hedef = tmp_path / "config.yaml"
    hedef.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    return load_config(hedef)


def _secici(secim):
    """Verilen değeri döndüren sahte seçim ekranı."""

    def _pick(choices, *, title, gradient_rows=False, stream=None):
        return secim

    return _pick


def _sirayla(*secimler):
    """Her çağrıda sıradaki değeri döndüren sahte seçim ekranı (çok adımlı akış)."""
    kalan = list(secimler)

    def _pick(choices, *, title, gradient_rows=False, stream=None):
        return kalan.pop(0)

    return _pick


# --------------------------------------------------------------------------- #
# /level
# --------------------------------------------------------------------------- #


def test_kademe_secilince_uygulanir(config):
    sonuc = model_flows.choose_level(config, picker=_secici("premium"))

    kademe = config.tier_by_name("premium")
    assert sonuc.config.agent == kademe.agent
    assert "premium" in sonuc.message


def test_kademe_secimi_dosyaya_yazilir(config):
    sonuc = model_flows.choose_level(config, picker=_secici("high"))

    assert load_config(config.source).agent == sonuc.config.agent


def test_kademe_secmekten_vazgecilince_yapilandirma_degismez(config):
    sonuc = model_flows.choose_level(config, picker=_secici(None))

    assert sonuc.config is config
    assert sonuc.message == messages.PICKER_CANCELLED


def test_vazgecilince_dosyaya_yazilmaz(config):
    onceki = config.source.read_text(encoding="utf-8")

    model_flows.choose_level(config, picker=_secici(None))

    assert config.source.read_text(encoding="utf-8") == onceki


def test_kademe_ekrani_gradyanli_cizilir(config):
    """Merdiven turuncudan pembeye boyanmalı; kaynak listesi boyanmamalı."""
    gorulen = {}

    def _pick(choices, *, title, gradient_rows=False, stream=None):
        gorulen["gradyan"] = gradient_rows
        return None

    model_flows.choose_level(config, picker=_pick)

    assert gorulen["gradyan"] is True


def test_kademe_ekrani_tum_kademeleri_sirasiyla_gosterir(config):
    gorulen = {}

    def _pick(choices, *, title, gradient_rows=False, stream=None):
        gorulen["degerler"] = [secim.value for secim in choices]
        return None

    model_flows.choose_level(config, picker=_pick)

    assert gorulen["degerler"] == [kademe.name for kademe in config.tiers]


def test_yazilamayan_dosya_kademeyi_geri_almaz(config, monkeypatch):
    """Dosya izni sorunu seçimi oturum boyunca kullanmayı engellememeli."""
    from fusion_cli.core.errors import ConfigError

    def _patla(cfg, path=None):
        raise ConfigError("izin yok")

    monkeypatch.setattr(model_flows.writer, "write_model_section", _patla)

    sonuc = model_flows.choose_level(config, picker=_secici("ultra"))

    assert sonuc.config.agent == config.tier_by_name("ultra").agent
    assert "izin yok" in sonuc.message


# --------------------------------------------------------------------------- #
# /development
# --------------------------------------------------------------------------- #


def test_kaynak_listesi_kullanicinin_istedigi_sirada(config):
    assert [kaynak.key for kaynak in model_flows.sources()] == [
        "openrouter-free",
        "nim-free",
        "openrouter-paid",
        "custom",
    ]


def test_ucretsiz_kaynaklar_ucretli_olandan_once_gelir(config):
    kaynaklar = model_flows.sources()

    ucretli = next(index for index, k in enumerate(kaynaklar) if k.paid)
    assert all(not k.paid for k in kaynaklar[:ucretli])


def test_katalogdan_model_secilince_uygulanir(config, monkeypatch):
    monkeypatch.setattr(
        model_flows.catalog,
        "fetch_openrouter_free",
        lambda: (CatalogEntry("openrouter/a/b:free", "openrouter", 128000),),
    )

    sonuc = model_flows.choose_development(
        config, picker=_sirayla("openrouter-free", "openrouter/a/b:free")
    )

    assert sonuc.config.agent.model == "openrouter/a/b:free"


def test_secilen_model_tum_rollere_uygulanir(config, monkeypatch):
    """Rollerden biri eski modelde kalsaydı sürpriz olurdu."""
    monkeypatch.setattr(
        model_flows.catalog,
        "fetch_openrouter_free",
        lambda: (CatalogEntry("openrouter/a/b:free", "openrouter", 0),),
    )

    sonuc = model_flows.choose_development(
        config, picker=_sirayla("openrouter-free", "openrouter/a/b:free")
    )

    assert sonuc.config.judge.model == "openrouter/a/b:free"
    assert [aday.model for aday in sonuc.config.candidates] == ["openrouter/a/b:free"]


def test_secilen_model_gorev_haritasina_da_islenir(config, monkeypatch):
    """Harita tanımsız adı işaret etseydi yazılan dosya bir daha yüklenemezdi."""
    monkeypatch.setattr(
        model_flows.catalog,
        "fetch_openrouter_free",
        lambda: (CatalogEntry("openrouter/a/b:free", "openrouter", 0),),
    )

    sonuc = model_flows.choose_development(
        config, picker=_sirayla("openrouter-free", "openrouter/a/b:free")
    )

    assert set(sonuc.config.task_model_map.values()) == {SINGLE_MODEL_NAME}
    assert load_config(config.source).agent.model == "openrouter/a/b:free"


def test_ucretli_kaynak_secilince_uyarilir(config, monkeypatch):
    monkeypatch.setattr(
        model_flows.catalog,
        "fetch_openrouter_paid",
        lambda: (CatalogEntry("openrouter/x/y", "openrouter", 200000),),
    )

    sonuc = model_flows.choose_development(
        config, picker=_sirayla("openrouter-paid", "openrouter/x/y")
    )

    assert messages.DEV_PAID_WARNING in sonuc.message


def test_ucretsiz_kaynakta_ucret_uyarisi_cikmaz(config, monkeypatch):
    monkeypatch.setattr(
        model_flows.catalog,
        "fetch_openrouter_free",
        lambda: (CatalogEntry("openrouter/a/b:free", "openrouter", 0),),
    )

    sonuc = model_flows.choose_development(
        config, picker=_sirayla("openrouter-free", "openrouter/a/b:free")
    )

    assert messages.DEV_PAID_WARNING not in sonuc.message


def test_ozel_model_alias_i_serbest_metinle_alinir(config):
    sonuc = model_flows.choose_development(
        config, picker=_secici("custom"), ask_text=lambda prompt: "ollama/qwen2.5-coder:7b"
    )

    assert sonuc.config.agent.model == "ollama/qwen2.5-coder:7b"


def test_gecersiz_alias_anlasilir_hata_verir(config):
    """Sağlayıcı öneki olmayan kimlik çağrı yönlendiremez."""
    sonuc = model_flows.choose_development(
        config, picker=_secici("custom"), ask_text=lambda prompt: "gpt-4"
    )

    assert sonuc.config is config
    assert "Geçersiz model kimliği" in sonuc.message


def test_bos_alias_vazgecmektir(config):
    sonuc = model_flows.choose_development(
        config, picker=_secici("custom"), ask_text=lambda prompt: "   "
    )

    assert sonuc.config is config
    assert sonuc.message == messages.PICKER_CANCELLED


def test_katalog_bos_donerse_sebebi_soylenir(config, monkeypatch):
    """Ağ yoksa ya da anahtar eksikse komut çökmemeli ama sessiz de kalmamalı."""
    monkeypatch.setattr(model_flows.catalog, "fetch_nim", tuple)

    sonuc = model_flows.choose_development(config, picker=_sirayla("nim-free"))

    assert sonuc.config is config
    assert sonuc.message == messages.DEV_EMPTY_CATALOG


def test_kaynak_secmekten_vazgecilebilir(config):
    sonuc = model_flows.choose_development(config, picker=_secici(None))

    assert sonuc.config is config
    assert sonuc.message == messages.PICKER_CANCELLED


def test_model_listesinde_baglam_uzunlugu_gosterilir(config, monkeypatch):
    """Bağlam uzunluğu seçimin en ayırt edici bilgisi."""
    gorulen = {}
    monkeypatch.setattr(
        model_flows.catalog,
        "fetch_openrouter_free",
        lambda: (CatalogEntry("openrouter/a/b:free", "openrouter", 128000),),
    )

    def _pick(choices, *, title, gradient_rows=False, stream=None):
        if title == messages.DEV_SOURCE_TITLE:
            return "openrouter-free"
        gorulen["aciklama"] = choices[0].description
        return None

    model_flows.choose_development(config, picker=_pick)

    assert "128.000" in gorulen["aciklama"]


# --------------------------------------------------------------------------- #
# Komut kaydı
# --------------------------------------------------------------------------- #


def test_iki_komut_da_kayitlidir():
    registry = build_registry()

    assert registry.get("level") is not None
    assert registry.get("development") is not None


def test_development_kisa_adiyla_da_cagrilir():
    assert build_registry().get("dev").name == "development"


def test_komutlar_kendi_islemcisinden_gecer():
    """İşi işleyici yapar; `RENDERED_COMMANDS` işleyiciyi hiç çağırmadan atlardı."""
    assert not {"level", "development"} & RENDERED_COMMANDS


def test_level_argumanla_ekran_acmadan_calisir(config, tmp_path):
    """Betiklenebilir yol: `/level premium` seçim ekranı açmamalı."""
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.memory.factory import null_memory

    state = ReplState(config=config, memory=null_memory(), root=tmp_path, home=tmp_path)
    registry = build_registry()
    _, arguman = parse("/level premium")

    sonuc = registry.get("level").handler(state, arguman)

    assert state.config.agent == config.tier_by_name("premium").agent
    assert "premium" in sonuc


def test_level_bilinmeyen_kademeyle_anlasilir_hata_verir(config, tmp_path):
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.memory.factory import null_memory

    state = ReplState(config=config, memory=null_memory(), root=tmp_path, home=tmp_path)

    sonuc = build_registry().get("level").handler(state, "yok-boyle")

    assert "kademe yok" in sonuc
    assert state.config is config


# --------------------------------------------------------------------------- #
# Katalog satırında profil uygunluk rozeti (Faz 2b)
# --------------------------------------------------------------------------- #


def test_buyuk_baglamli_model_tum_profillere_rozetlenir(config):
    entry = CatalogEntry(model_id="a/b", provider="p", context_length=200000)
    etiket = model_flows._model_label(entry, config.profile_eligibility)
    assert "low" in etiket and "medium" in etiket and "high" in etiket and "max" in etiket


def test_kucuk_baglamli_model_ust_profillerde_gorunmez(config):
    entry = CatalogEntry(model_id="a/b", provider="p", context_length=32000)
    etiket = model_flows._model_label(entry, config.profile_eligibility)
    assert "low" in etiket and "medium" in etiket
    assert "high" not in etiket and "max" not in etiket


def test_bilinmeyen_baglam_tum_profillerde_gorunur(config):
    # Bağlam 0 (bilinmiyor) → gerçekçilik kuralı gereği gizlenmez.
    entry = CatalogEntry(model_id="a/b", provider="p", context_length=0)
    etiket = model_flows._model_label(entry, config.profile_eligibility)
    assert "high" in etiket and "max" in etiket


def _config_with_web_session(config):
    from dataclasses import replace

    from fusion_cli.config.models import WebSessionConfig

    session = WebSessionConfig(
        model="chatgpt_web/main/auto",
        provider="chatgpt_web",
        account="main",
        transport="browser",
        credential_ref="WEB_SECRET::chatgpt_web::main",
        tool_support="emulated",
        headless=True,
        timeout_s=180.0,
        enabled=True,
    )
    return replace(config, web_sessions=(session,))


def test_web_oturumu_kaynak_olarak_gorunur_ve_bulunur(config):
    """Panelde bağlanan web oturumu `/development` kaynak listesinde çıkmalı."""
    web_config = _config_with_web_session(config)

    keys = [choice.value for choice in model_flows.source_choices(web_config)]
    assert "web-subscriptions" in keys
    source = model_flows.source_by_key(web_config, "web-subscriptions")
    assert source is not None
    assert source.fetcher is not None
    assert model_flows.source_by_key(web_config, "yok-boyle") is None


def test_web_oturumu_secilince_tum_rollere_uygulanir(config):
    """TUI ve plain REPL'in ortak kullandığı uygulama fonksiyonu web modelini bağlamalı."""
    web_config = _config_with_web_session(config)

    sonuc = model_flows.apply_development_model(web_config, "chatgpt_web/main/auto", paid=False)

    assert sonuc.config.agent.model == "chatgpt_web/main/auto"
    assert sonuc.config.judge.model == "chatgpt_web/main/auto"
    assert load_config(config.source).agent.model == "chatgpt_web/main/auto"
    assert messages.DEV_PAID_WARNING not in sonuc.message


def test_apply_development_model_ucretli_uyari_ekler(config):
    sonuc = model_flows.apply_development_model(config, "openrouter/x/y", paid=True)

    assert sonuc.config.agent.model == "openrouter/x/y"
    assert messages.DEV_PAID_WARNING in sonuc.message


def test_apply_development_model_strict_tek_model_secimi_yapar(config):
    sonuc = model_flows.apply_development_model(config, "gemini_web/main/auto", paid=False)

    assert sonuc.config.agent.strict is True
    assert sonuc.config.agent.models == ("gemini_web/main/auto",)


def test_strict_agent_task_model_mapten_ustundur(config):
    from dataclasses import replace

    from fusion_cli.config.model_select import select_agent_spec
    from fusion_cli.core.types import ModelSpec

    strict_agent = ModelSpec(name="secilen", model="gemini_web/main/auto", tags=("strict",))
    mapped_candidate = ModelSpec(name="eski", model="nvidia_nim/openai/gpt-oss-120b")
    updated = replace(
        config,
        agent=strict_agent,
        candidates=(mapped_candidate,),
        task_model_map={"general": "eski"},
    )

    assert select_agent_spec(updated, "general") == strict_agent


def test_apply_development_model_gecersiz_kimlik_config_i_degistirmez(config):
    sonuc = model_flows.apply_development_model(config, "gecersiz", paid=False)

    assert sonuc.config is config
    assert "Geçersiz model kimliği" in sonuc.message


def test_entries_to_choices_kimlik_ve_rozet_uretir(config):
    entries = (CatalogEntry("chatgpt_web/main/auto", "chatgpt_web", 0),)

    choices = model_flows.entries_to_choices(entries, config.profile_eligibility)

    assert choices[0].value == "chatgpt_web/main/auto"
    assert choices[0].label == "chatgpt_web/main/auto"


def test_tui_gelistirme_komutunu_argumansiz_engellemez():
    """TUI artık `/development`'ı 'argüman ister' diye reddetmemeli; modalla açar."""
    from fusion_cli.cli.repl.tui_loop import _would_open_picker

    assert _would_open_picker("development", "") is False
    assert _would_open_picker("provider", "") is True


def test_katalog_yetenegi_baglami_tasir_araci_bilinmez():
    from fusion_cli.core.model_capability import ToolSupport

    cap = model_flows.catalog_capability(
        CatalogEntry(model_id="a/b", provider="p", context_length=64000)
    )
    assert cap.context_window == 64000
    assert cap.tool_support is ToolSupport.UNKNOWN


def test_gelistirme_akisinda_secilen_model_rozetle_uygulanir(config, monkeypatch):
    entries = (
        CatalogEntry(model_id="openrouter/a/b:free", provider="openrouter", context_length=200000),
    )
    monkeypatch.setattr(model_flows.catalog, "fetch_openrouter_free", lambda: entries)
    gorulen = {}

    def _pick(choices, *, title, gradient_rows=False, stream=None):
        # İlk çağrı kaynak seçimi (tek elemanlı Choice.key kaynak anahtarı),
        # ikinci çağrı model seçimi. Model listesini yakala.
        if choices[0].value == "openrouter-free":
            return "openrouter-free"
        gorulen["choices"] = choices
        return "openrouter/a/b:free"

    sonuc = model_flows.choose_development(config, picker=_pick)
    assert sonuc.config.agent.model == "openrouter/a/b:free"
    # Seçim satırında profil rozeti göründü.
    assert any("profiller" in choice.description for choice in gorulen["choices"])
