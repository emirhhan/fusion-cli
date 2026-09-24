"""Doğrulanmamış taklit-araç modeli dosya değiştiremez.

`config/tool_policy.py` bunu belgeliyordu ama kod uygulamıyordu:

- Yetenek `ModelSpec` ETİKETLERİNDEN türetiliyordu; panelden bağlanan bir web
  oturumunun `tool_support` alanı hiç okunmuyordu. Etiketsiz model `UNKNOWN` sayılıp
  mutation'a giriyordu.
- `select_agent_spec` içindeki `strict` kısa devresi kontrolü tamamen atlıyordu:
  panelden "zorunlu model" seçmek güvenlik kapısını atlamak demekti.

Karar kullanıcıya sorulmaz — bu bir onay meselesi değil, YETENEK meselesidir.
"""

from __future__ import annotations

import pytest

from fusion_cli.config.models import WebSessionConfig
from fusion_cli.config.tool_policy import mutation_policy_for_model
from fusion_cli.core.events import MutationUnavailable
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.execution_policy import policy_for, refresh_mutation_policy
from fusion_cli.engines.agent.loop import AgentDeps, run_agent
from fusion_cli.engines.effects.detect import required_effect_for

from .fakes import AlwaysApprove, RecordingSink, ScriptedProvider, make_config, model_result


class _Publisher:
    def __init__(self, sink):
        self._sink = sink

    def publish(self, event):
        self._sink.handle(event)


WEB_MODEL = "chatgpt_web/main/auto"


def _config(**session_overrides):
    alanlar = {
        "model": WEB_MODEL,
        "provider": "chatgpt_web",
        "account": "main",
        "transport": "browser",
        "tool_support": "emulated",
    }
    config_overrides = {
        key: session_overrides.pop(key) for key in list(session_overrides) if key == "agent"
    }
    alanlar.update(session_overrides)
    return make_config(web_sessions=(WebSessionConfig(**alanlar),), **config_overrides)


def test_dogrulanmamis_taklit_arac_modeli_mutation_yapamaz():
    policy = mutation_policy_for_model(_config(), WEB_MODEL)

    assert policy.ok is False
    assert "eval" in policy.reason


def test_eval_esigini_gecen_model_mutation_yapabilir():
    policy = mutation_policy_for_model(_config(tool_eval_passed=True), WEB_MODEL)

    assert policy.ok is True


def test_aracsiz_web_oturumu_mutation_yapamaz():
    policy = mutation_policy_for_model(_config(tool_support="none"), WEB_MODEL)

    assert policy.ok is False
    assert "araç desteği yok" in policy.reason


def test_web_oturumu_olmayan_model_etkilenmez():
    """API modelleri bu kapıdan geçmez; davranışları birebir korunur."""
    assert mutation_policy_for_model(_config(), "nvidia_nim/nvidia/nemotron").ok is True


def test_strict_secim_guvenlik_kapisini_atlayamaz():
    """Panelden "zorunlu model" seçmek yetenek kapısını devre dışı bırakamaz."""
    config = _config()
    strict_spec = ModelSpec(name="web", model=WEB_MODEL, tags=("strict",))

    execution = policy_for(config, strict_spec, "dosyayı düzelt")

    assert execution.allow_mutation is False
    assert execution.mutation_block_reason


def test_eval_gecmisse_yurutme_politikasi_izin_verir():
    config = _config(tool_eval_passed=True)
    spec = ModelSpec(name="web", model=WEB_MODEL, tags=("strict",))

    execution = policy_for(config, spec, "dosyayı düzelt")

    assert execution.allow_mutation is True


def test_api_modeli_varsayilan_olarak_mutation_yapabilir():
    config = make_config()
    spec = ModelSpec(name="agent", model="nvidia_nim/x")

    execution = policy_for(config, spec, "dosyayı düzelt")

    assert execution.allow_mutation is True


# --- Kısıt SESSİZ kalmamalı --------------------------------------------------- #
#
# Gerçek kullanım: kullanıcı Gemini web oturumuna "arkadaki uygulamayı kapat" dedi.
# Model "böyle bir aracım yok" dedi ve HAKLIYDI — run_shell şeması ona hiç
# sunulmamıştı. Ama kısıtın nereden geldiği hiçbir yerde görünmüyordu ve kullanıcı
# Fusion'ı arızalı sandı.


async def test_arka_plan_uygulamasini_kapatma_gercek_eylem_sayilir():
    """'kapat' hiçbir desende yoktu; istek sohbet sanılıyordu."""
    assert required_effect_for("arkada çalışan bir uygulamayı kapat") == "shell_action"
    assert required_effect_for("arkaplandaki uygulamayı kapat") == "shell_action"
    assert required_effect_for("uygulamayı sonlandır") == "shell_action"


async def test_dosya_ya_da_pencere_kapatmak_sistem_eylemi_sayilmaz():
    """Aşırı yakalama, sohbeti araç turuna çevirirdi."""
    assert required_effect_for("bu dosyayı kapat") is None
    assert required_effect_for("pencereyi kapat") is None
    assert required_effect_for("tarayıcıyı kapatma") is None


async def test_yapilamayacak_eylemde_tur_model_cagirmadan_biter(tmp_path):
    """Model çağrısı harcanmaz ve kullanıcıya ne yapacağı söylenir."""
    sink = RecordingSink()
    cagrilar = {"sayi": 0}

    class _Sayan:
        label = "gemini"

        async def stream(self, request):
            cagrilar["sayi"] += 1
            raise AssertionError("model hiç çağrılmamalıydı")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(agent_loop, "build_provider", lambda spec, **kw: _Sayan())
    try:
        deps = AgentDeps(
            config=_config(agent=ModelSpec(name="web", model=WEB_MODEL, tags=("strict",))),
            publisher=_Publisher(sink),
            policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
            tool_context=ToolContext(root=tmp_path),
        )
        sonuc = await run_agent("arkadaki uygulamayı kapat", deps)
    finally:
        monkeypatch.undo()

    assert cagrilar["sayi"] == 0
    assert not sonuc.ok
    assert "Araç yeteneğini ölç" in sonuc.final_text
    assert "Hiçbir değişiklik yapılmadı" in sonuc.final_text
    olay = next(e for e in sink.events if isinstance(e, MutationUnavailable))
    assert olay.blocking is True


async def test_salt_okunur_kip_sohbet_turunda_da_bildirilir(tmp_path, monkeypatch):
    """Görev eylem istemese bile kullanıcı salt-okunur kipte olduğunu görmeli."""
    sink = RecordingSink()
    monkeypatch.setattr(
        agent_loop,
        "build_provider",
        lambda spec, **kw: ScriptedProvider([model_result("liste değiştirilebilir.")]),
    )
    deps = AgentDeps(
        config=_config(agent=ModelSpec(name="web", model=WEB_MODEL, tags=("strict",))),
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )

    await run_agent("liste ile demet farkı nedir", deps)

    olay = next(e for e in sink.events if isinstance(e, MutationUnavailable))
    assert olay.blocking is False


async def test_salt_okuma_istegi_degistiremeyen_modelde_de_cevaplanir(tmp_path, monkeypatch):
    """Okuma isteği, değişiklik yapamayan modelde erken bitmemeli.

    Ölçüldü (19 Eylül G7 gerçek koşusu): "siparis.py'deki akışı incele ve anlat"
    `workspace_read` etkisi aldığı için kapı turu model çağırmadan bitirdi ve
    kullanıcıya "dosya/sistem değişikliği gerektiriyor" dedi. Okuma değişiklik
    değildir: model çağrılır, yalnız değiştirici araçlar sunulmaz.
    """
    sink = RecordingSink()
    monkeypatch.setattr(
        agent_loop,
        "build_provider",
        lambda spec, **kw: ScriptedProvider([model_result("Akış sepetten kargoya gider.")]),
    )
    deps = AgentDeps(
        config=_config(agent=ModelSpec(name="web", model=WEB_MODEL, tags=("strict",))),
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )

    sonuc = await run_agent("siparis.py dosyasındaki sipariş akışını incele ve anlat", deps)

    # Erken "değişiklik gerekiyor" cevabı YOK; model çağrıldı. Modelin dosyayı
    # okumadan cevaplaması ayrı bir kapıdır (okuma kanıtı) ve burada sınanmaz.
    assert "Araç yeteneğini ölç" not in sonuc.final_text
    assert "Hiçbir değişiklik yapılmadı" not in sonuc.final_text
    assert sonuc.model_calls_made >= 1
    olay = next(e for e in sink.events if isinstance(e, MutationUnavailable))
    assert olay.blocking is False


# --- Ölçüm sonucu ve tür temelli engelleme ------------------------------------ #


async def test_kod_duzeltme_gorevi_mutation_kapaliyken_erken_biter(tmp_path, monkeypatch):
    """Metinden effect çıkarılamasa bile BUGFIX türü değişiklik ister.

    Gerçek koşu: "envanter.py'deki hataları düzelt ve eksik dogrulama modülünü yaz"
    hiçbir effect desenine uymuyordu; tur salt-okunur kipte beş çağrı harcayıp
    hiçbir şey yapamadan bitti.
    """
    sink = RecordingSink()

    class _Patlayan:
        label = "web"

        async def stream(self, request):
            raise AssertionError("model hiç çağrılmamalıydı")

    monkeypatch.setattr(agent_loop, "build_provider", lambda spec, **kw: _Patlayan())
    deps = AgentDeps(
        config=_config(agent=ModelSpec(name="web", model=WEB_MODEL, tags=("strict",))),
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )

    sonuc = await run_agent(
        "envanter.py'deki hataları düzelt ve eksik dogrulama modülünü yaz", deps
    )

    assert not sonuc.ok
    assert "Araç yeteneğini ölç" in sonuc.final_text
    olay = next(e for e in sink.events if isinstance(e, MutationUnavailable))
    assert olay.blocking is True


def test_calisir_hale_getirme_workspace_mutation_ister():
    """Kanıt kapısının kurulması buna bağlı: etki yoksa "yaptım" denetlenmez."""
    assert required_effect_for("dashboard'ı çalışır hale getir") == "workspace_mutation"
    assert required_effect_for("iki projeyi entegre et") == "workspace_mutation"


def test_ingilizce_uzun_kod_gorevi_de_degisim_kaniti_ister():
    task = (
        "Investigate the existing stock types and tests. Implement a coherent "
        "stock import flow with missing modules and route changes. Run TypeScript."
    )
    assert required_effect_for(task) == "workspace_mutation"
    assert required_effect_for("How to implement a stock import flow?") is None
    assert required_effect_for("What steps would implement a stock import flow?") is None
    assert required_effect_for("Can you implement a stock import flow?") == "workspace_mutation"


def test_calisir_hale_getirme_sorusu_etki_istemez():
    assert required_effect_for("bu panel nasıl çalışır hale getirilir") is None


def test_arayuz_ogesi_ekleme_istegi_mutasyon_sayilir():
    """ "rozetin yanına bir span ekle" bir okuma isteği değildir.

    Ölçüldü (canlı koşu): bu istek hiçbir nesne desenine uymuyordu, görev
    `workspace_read` sanıldı ve BEŞ araç turluk keşif bütçesine düştü; tur
    "araç turu sınırına ulaşıldı (5)" ile kesildi.
    """
    istek = "Sistem durumu rozetinin yanina 'Son guncelleme: <saat>' gosteren kucuk bir span ekle."

    assert required_effect_for(istek) == "workspace_mutation"


def test_degistirici_arac_adi_gecerse_mutasyon_sayilir():
    """Kullanıcı aracı adıyla söylediyse tartışma biter."""
    assert required_effect_for("hedefli edit_file kullan") == "workspace_mutation"
    assert required_effect_for("write_file ile oluştur") == "workspace_mutation"


def test_salt_okuma_istegi_mutasyon_sayilmaz():
    """Genişletme salt-okuma isteklerini mutasyona çevirmemeli."""
    assert required_effect_for("klasörü listele") == "workspace_read"
    assert required_effect_for("src/app.py dosyasını oku ve açıkla") is None


def test_nesnesiz_duzelt_fiili_de_mutasyon_sayilir():
    """Fiilin yanında nesne olmayabilir; nesne iki cümle önce geçebilir.

    Ölçüldü: "Ustune binmenin sebebini tespit et ve duzelt" cümlesinde fiilin
    yanında hiçbir nesne yok. Görev `workspace_read` sanıldı, sekiz model
    çağrılık sohbet bütçesine düştü ve iş tam ilerlerken "model çağrısı sınırına
    ulaşıldı (8)" ile kesildi.
    """
    assert required_effect_for("Ustune binmenin sebebini tespit et ve duzelt") == (
        "workspace_mutation"
    )
    assert required_effect_for("bunu güncelle") == "workspace_mutation"


def test_cok_anlamli_fiiller_listede_degil():
    """ "cevap yaz" bir dosya değişikliği değildir; liste dar tutulur."""
    assert required_effect_for("kısa bir cevap yaz") != "workspace_mutation"


def test_ad_soyleme_istegi_mutasyon_sayilmaz():
    """ "kod adını yaz" bir SORU cevabı istemidir, dosya değişikliği değildir.

    Ölçüldü (18 Eylül, `/plan-yurut` duraklamasından sonraki tur): kullanıcı
    "Projenin kod adı neydi? Yalnız kod adını yaz." dedi. `kod` nesnesi
    (`_MUTATION_OBJECTS` içinde, çünkü "kod ekle/düzelt" GERÇEK bir mutasyondur)
    cümlede `yaz` fiilinden 50 karakter önce geçtiği için tur workspace_mutation
    sayıldı; kanıt kapısı gerçek bir dosya değişikliği istedi ve model soruyu
    cevaplamak yerine ilgisiz bir dosyayı düzenleyip "kanıt" üretmeye çalıştı.
    Asıl fiilin nesnesi `kod` değil `adını` (bir isim/cevap istemi).
    """
    assert required_effect_for("Projenin kod adı neydi? Yalnız kod adını yaz.") != (
        "workspace_mutation"
    )
    assert required_effect_for("sadece projenin ismini yaz") != "workspace_mutation"
    # Gerçek kod-yazma isteği hâlâ mutasyon sayılmalı: fiilin nesnesi burada
    # "adı" değil doğrudan "kod"un kendisi.
    assert required_effect_for("bu fonksiyonun kodunu yaz") == "workspace_mutation"


# --- yedeğe düşen tur ------------------------------------------------------ #


def _web_policy(**session_overrides):
    """Web oturumu birincilken kurulan tur politikası."""
    return policy_for(
        _config(**session_overrides), ModelSpec(name="web", model=WEB_MODEL), "dosyayı düzenle"
    )


def test_yedege_dusen_tur_yazabilen_modele_gecince_kapi_acilir():
    """Zincir yazabilen bir modele düştüyse salt-okunur kilit kalkar.

    Ölçüldü (22 Eylül, kullanıcının kendi kurulumunda): birincil `chatgpt_web`
    oturumu insan doğrulamasına takılınca zincir `nvidia_nim/...` modeline düştü
    ve tur sonuna kadar SALT-OKUNUR kaldı — oysa engelin gerekçesi artık işi
    yapan modele ait değildi.
    """
    config = _config()
    politika = _web_policy()
    assert politika.allow_mutation is False

    tazelenmis = refresh_mutation_policy(
        politika, "nvidia_nim/nemotron-3-ultra-550b-a55b", config
    )

    assert tazelenmis.allow_mutation is True
    assert tazelenmis.mutation_block_reason == ""


def test_ayni_yeteneksiz_model_karsiladiysa_kapi_kapali_kalir():
    config = _config()

    tazelenmis = refresh_mutation_policy(_web_policy(), WEB_MODEL, config)

    assert tazelenmis.allow_mutation is False
    assert "eval" in tazelenmis.mutation_block_reason


def test_hizmet_veren_model_bilinmiyorsa_kapi_kapali_kalir():
    """`served_by` boşsa tahmin edilmez: ölçülmemiş yeteneğe yazma izni verilmez."""
    config = _config()

    assert refresh_mutation_policy(_web_policy(), "", config).allow_mutation is False


def test_gozlem_turunun_kilidi_yedek_degisikligiyle_acilmaz():
    """Kip kararı yetenek kararı DEĞİLDİR: gözlem turu yazmaya açılamaz."""
    from fusion_cli.engines.agent.chat_mode import observe_execution

    config = _config()
    gozlem = observe_execution(_web_policy(), "bu adım yalnız gözlemler")

    tazelenmis = refresh_mutation_policy(
        gozlem, "nvidia_nim/nemotron-3-ultra-550b-a55b", config
    )

    assert tazelenmis.allow_mutation is False


def test_sohbet_turunun_kilidi_yedek_degisikligiyle_acilmaz():
    from fusion_cli.engines.agent.chat_mode import chat_execution

    config = _config()
    sohbet = chat_execution(_web_policy())

    tazelenmis = refresh_mutation_policy(
        sohbet, "nvidia_nim/nemotron-3-ultra-550b-a55b", config
    )

    assert tazelenmis.allow_mutation is False
