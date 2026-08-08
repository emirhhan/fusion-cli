"""Çıktı sözleşmesi — gerçek bir başarısızlığın uçtan uca regresyonu.

Bu dosya tek bir gerçek koşuyu kilitler. Kullanıcı bağlı projelerin analizini ve
bir panelin çalışır hale getirilmesini istedi; model iki dosya OKUDU, hiçbir şey
yazmadı ve "entegrasyon betiklerini hazırladım, değişen dosyalar: package.json"
diyerek turu bitirdi. Dosyaların hiçbiri değişmemişti — model okuduğu dosyada
zaten var olan bir betiği kendi işi gibi raporlamıştı.

Aynı koşuda üç davranış daha bozuktu: öncü metin hiç görünmüyordu, model taşıma
çerçevesinin rol başlığını (`FUSION//…`) cevabına taşıyordu ve iş yapmadan
kullanıcıya "ne yapmamı istersiniz" diye soruyordu.

Buradaki testler o dört davranışı ayrı ayrı değil, gerçek prompt üzerinden ve
gerçek kapılarla ölçer. Sahte olan TEK şey sağlayıcıdır; sınıflandırma, etki
tespiti, kanıt kapısı, araç kayıt defteri ve dosya sistemi gerçektir.
"""

from __future__ import annotations

import json

from fusion_cli.core.model_capability import ToolSupport
from fusion_cli.core.tool_emulation import CALL_CLOSE, CALL_OPEN
from fusion_cli.core.types import CompletionRequest, Message, TextChunk
from fusion_cli.engines.agent import reflexion
from fusion_cli.engines.agent.classify import TaskKind, classify_task
from fusion_cli.engines.agent.execution_policy import policy_for
from fusion_cli.engines.agent.loop import run_agent
from fusion_cli.engines.effects.detect import required_effect_for
from fusion_cli.providers.web_browser import format_browser_prompt, strip_role_headers
from fusion_cli.providers.web_session import WebProviderAdapter, WebSessionCredential

from .agent_harness import WEB_MODEL, install_provider, web_deps
from .fakes import RecordingSink, make_config, model_result, tool_call

#: Kullanıcının gerçekte yazdığı istek. Kısaltılmadı: sınıflandırma ve etki
#: tespiti tam metin üzerinde ölçülmeli.
GERCEK_ISTEK = (
    "bu projenin bağlı olduğu diğer projeleri analiz et bu projenin bağlı olduğu "
    "projeleri tüm fonksiyonlarıyla eksiksiz kontrol edebilmesini istiyorum ve "
    "gate-ai projesinde bulunan dashboard ı yani meta panelini de tüm "
    "fonksiyonlarıyla çalışır bir hale getirmesini istiyorum."
)

#: Modelin gerçekte verdiği uydurma teslim raporu.
UYDURMA_TESLIM = (
    "Projenin bağlı olduğu yan projeleri ve package.json yapısını inceledim. Yan "
    "projeler olan market-analyzer ve baffer dizinleriyle entegrasyon betiklerini "
    "hazırladım, gate-ai projesindeki meta paneli ve tüm fonksiyon yönetim "
    "arayüzünü güncelledim.\n\nDeğişen dosyalar: package.json ve ilgili monorepo "
    "entegrasyon betikleri."
)


# --- 1. görev doğru sınıflanır, kapılar kurulur ---------------------------- #


def test_istek_kod_degistiren_is_olarak_taninir():
    """Her şey buna bağlı: yanlış sınıflanan istekte hiçbir kapı kurulmuyordu."""
    assert classify_task(GERCEK_ISTEK) is TaskKind.FEATURE
    assert required_effect_for(GERCEK_ISTEK) == "workspace_mutation"


def test_kanit_ve_karmasiklik_kapilari_acilir():
    config = make_config()
    policy = policy_for(config, config.agent, classify_task(GERCEK_ISTEK), GERCEK_ISTEK)

    assert policy.requires_tool_evidence is True
    assert policy.complex_task is True


# --- 2. kanıtsız "yaptım" teslim edilmez ----------------------------------- #


async def test_uydurma_teslim_kanitsiz_gecmez(monkeypatch, tmp_path):
    """Model yalnızca OKUYUP "değiştirdim" derse tur başarıyla kapanmamalı."""
    sink = RecordingSink()
    install_provider(
        monkeypatch,
        _Scripted(
            [
                model_result(tool_calls=[tool_call("list_dir", path=".")]),
                model_result(tool_calls=[tool_call("list_dir", path="app")]),
                model_result(UYDURMA_TESLIM),
                model_result(UYDURMA_TESLIM),
            ]
        ),
    )

    sonuc = await run_agent(GERCEK_ISTEK, web_deps(tmp_path, sink))

    assert sonuc.mutating_tool_calls_made == 0
    assert sonuc.final_text != UYDURMA_TESLIM, "kanıtsız teslim olduğu gibi geçti"


async def test_degisiklik_yapilmayan_tur_isaretlenir(monkeypatch, tmp_path):
    """Rozetin koşulu: okudu, hiçbir şey değiştirmedi."""
    sink = RecordingSink()
    install_provider(
        monkeypatch,
        _Scripted(
            [
                model_result(tool_calls=[tool_call("list_dir", path=".")]),
                model_result(UYDURMA_TESLIM),
                model_result(UYDURMA_TESLIM),
            ]
        ),
    )

    sonuc = await run_agent(GERCEK_ISTEK, web_deps(tmp_path, sink))

    assert sonuc.made_no_changes is True


# --- 3. iş yapmadan soru sorarak bitirilmez -------------------------------- #


#: Modeli tekrar iş başına gönderen düzeltici notlar. Hangisinin devreye gireceği
#: göreve bağlıdır (kanıt kapısı, otomatik devam, "iş yapmadan sordu"); sözleşme
#: belirli bir notu değil, TURUN ORADA BİTMEMESİNİ şart koşar.
_DUZELTICI_NOTLAR = (
    reflexion.ASKED_INSTEAD_OF_ACTING_NOTE,
    reflexion.AUTO_CONTINUE_NOTE,
)

SORU_CEVABI = "Dizin yapısı incelendi. Ne yapmak istediğinizi belirtin?"


async def test_ne_yapayim_sorusu_turu_bitirmez(monkeypatch, tmp_path):
    sink = RecordingSink()
    provider = install_provider(
        monkeypatch,
        _Scripted(
            [
                model_result(tool_calls=[tool_call("list_dir", path=".")]),
                model_result(SORU_CEVABI),
                model_result("`app/page.tsx` okundu; devam ediyorum."),
            ]
        ),
    )

    sonuc = await run_agent(GERCEK_ISTEK, web_deps(tmp_path, sink))

    assert provider.calls >= 3, "soru sorup duran tur zorlanmadı"
    assert sonuc.final_text != SORU_CEVABI, "soru kullanıcıya nihai cevap olarak döndü"
    duzeltildi = any(
        mesaj.content in _DUZELTICI_NOTLAR or "kanıt" in mesaj.content.lower()
        for mesaj in sonuc.messages
        if mesaj.role == "user"
    )
    assert duzeltildi, "model tekrar iş başına gönderilmedi"


async def test_soru_kapisi_kanit_kapisi_olmadan_da_calisir(monkeypatch, tmp_path):
    """Kanıt kapısı kurulmayan bir görevde soru kapısı tek başına tutmalı.

    İki kapı üst üste bindiği için asıl kapının çalıştığı görünmüyordu; burada
    etki sözleşmesi üretmeyen bir istekle yalnız bırakılıyor.
    """
    sink = RecordingSink()
    provider = install_provider(
        monkeypatch,
        _Scripted(
            [
                model_result(tool_calls=[tool_call("list_dir", path=".")]),
                model_result(SORU_CEVABI),
                model_result("`app/page.tsx` içeriği şu şekilde."),
            ]
        ),
    )

    sonuc = await run_agent("projedeki dizinlere bak", web_deps(tmp_path, sink))

    assert provider.calls >= 3
    assert any(
        mesaj.content == reflexion.ASKED_INSTEAD_OF_ACTING_NOTE for mesaj in sonuc.messages
    )


# --- 4. öncü metin görünür, çerçeve sızmaz --------------------------------- #


async def test_arac_turundaki_oncu_cumle_kullaniciya_akar():
    blok = json.dumps({"name": "list_dir", "arguments": {"path": "."}})
    reply = f"Bağlı projeleri bulmak için dizini tarıyorum. {CALL_OPEN}{blok}{CALL_CLOSE}"

    async def _transport(credential, messages, model):
        return reply

    adapter = WebProviderAdapter(
        model=WEB_MODEL,
        credential=WebSessionCredential(),
        transport=_transport,
        tool_support=ToolSupport.EMULATED,
    )
    request = CompletionRequest(
        messages=(Message("user", GERCEK_ISTEK),),
        temperature=0.0,
        max_tokens=256,
        timeout_s=5.0,
        tools=({"type": "function", "function": {"name": "list_dir", "parameters": {}}},),
    )

    parcalar = [item async for item in adapter.stream(request) if isinstance(item, TextChunk)]

    assert [parca.text for parca in parcalar] == ["Bağlı projeleri bulmak için dizini tarıyorum."]


def test_rol_basligi_cevaba_tasinmaz():
    cevap = "### FUSION//SONRAKİ ADIM\nMevcut dizin yapısı incelenmiştir."

    assert strip_role_headers(cevap) == "Mevcut dizin yapısı incelenmiştir."


def test_prompt_uydurma_teslimi_yasaklar():
    prompt = format_browser_prompt((Message("user", GERCEK_ISTEK),))

    assert "YALNIZCA bu turda gerçekten çağırdığın araçlarla" in prompt
    assert "ask_user" in prompt


class _Scripted:
    """Sırayla yanıt veren sağlayıcı; liste biterse sonuncuyu tekrarlar.

    `ScriptedProvider` liste tükenince patlar. Kapılar turu UZATABİLDİĞİ için
    (kanıt yeniden-sorma, otomatik devam) buradaki testlerde kaç çağrı olacağı
    sabit değildir; ölçülen şey çağrı sayısı değil turun nasıl bittiğidir.
    """

    def __init__(self, results):
        self._results = list(results)
        self.calls = 0

    @property
    def label(self) -> str:
        return WEB_MODEL

    async def complete(self, request):
        index = min(self.calls, len(self._results) - 1)
        self.calls += 1
        return self._results[index]

    async def stream(self, request):
        from fusion_cli.core.types import StreamDone

        yield StreamDone(await self.complete(request))
