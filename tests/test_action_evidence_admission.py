"""Çalışma turu, sağlayıcıdan bağımsız gerçek işlem kanıtı ister."""

from dataclasses import replace

import pytest

from fusion_cli.core.types import Message, ModelSpec
from fusion_cli.engines.agent.loop import run_agent
from tests.agent_harness import install_provider
from tests.fakes import RecordingSink, ScriptedProvider, model_result, tool_call
from tests.test_web_execution_policy import _deps

MODELS = ("ollama_chat/test", "openai/test", "gemini_web/test")
TASK = (
    "tamamdır şimdi çalışmaya başla ve tam bir çeviri yap ve ben oyunu açtığımda "
    "çevirilmemiş veya hatalı çevirilmiş hiçbir yer görmek istemiyorum "
    "o sorunu da çöz fonttan dolayı görünmeyen türkçe harfler olmasın"
)
LIE = "Font katmanı eklendi. Yazı tipi sorununu düzelttim. Oyunu yeniden açman yeterli."


def deps_for(tmp_path, model):
    deps = _deps(tmp_path, RecordingSink())
    deps.config = replace(deps.config, agent=ModelSpec(name="agent", model=model))
    return deps


@pytest.mark.parametrize("model", MODELS)
async def test_calismaya_baslama_aracsiz_basari_sayilmaz(tmp_path, monkeypatch, model):
    provider = ScriptedProvider([model_result(LIE)] * 4)
    install_provider(monkeypatch, provider)
    result = await run_agent(TASK, deps_for(tmp_path, model))
    assert not result.ok
    assert LIE not in result.final_text
    assert result.tool_calls_made == 0


@pytest.mark.parametrize("model", MODELS)
async def test_siniflandirilmayan_istekte_yalan_islem_iddiasi_da_engellenir(
    tmp_path, monkeypatch, model
):
    install_provider(monkeypatch, ScriptedProvider([model_result(LIE)] * 4))
    result = await run_agent("bir el at", deps_for(tmp_path, model))
    assert not result.ok
    assert LIE not in result.final_text


@pytest.mark.parametrize("model", MODELS)
async def test_kanit_uyarisindan_sonra_gercek_aracla_is_yapilir(tmp_path, monkeypatch, model):
    provider = ScriptedProvider(
        [
            model_result(LIE),
            model_result(tool_calls=[tool_call("write_file", path="font.txt", content="Türkçe")]),
            model_result("font.txt dosyasını güncelledim."),
        ]
    )
    install_provider(monkeypatch, provider)
    result = await run_agent("bir el at", deps_for(tmp_path, model))
    assert result.ok
    assert (tmp_path / "font.txt").read_text() == "Türkçe"
    assert result.mutating_tool_calls_made == 1


async def test_devam_istegi_onceki_kullanici_isinin_kanitini_ister(tmp_path, monkeypatch):
    install_provider(
        monkeypatch, ScriptedProvider([model_result("Tamam."), model_result("Tamam.")])
    )
    history = [
        Message("user", "font.txt dosyasını güncelle"),
        Message("assistant", "Başlıyorum."),
        Message("user", "yalnızca cevap yaz", harness_note=True),
    ]
    result = await run_agent("devam et", deps_for(tmp_path, "openai/test"), history=history)
    assert not result.ok
    assert result.mutating_tool_calls_made == 0


@pytest.mark.parametrize("task", ["merhaba", "sadece TAMAM yaz", "önceki işte ne yaptın?"])
async def test_yeni_soru_eski_mutasyonu_miras_almaz(tmp_path, monkeypatch, task):
    install_provider(monkeypatch, ScriptedProvider([model_result("Yanıt.")]))
    result = await run_agent(
        task,
        deps_for(tmp_path, "openai/test"),
        history=[Message("user", "font.txt dosyasını güncelle")],
    )
    assert result.ok
    assert result.final_text == "Yanıt."


async def test_okuma_kaniti_yazma_iddiasini_dogrulamaz(tmp_path, monkeypatch):
    install_provider(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("list_dir", path=".")]),
                *[model_result(LIE)] * 4,
            ]
        ),
    )
    result = await run_agent("bir el at", deps_for(tmp_path, "openai/test"))
    assert not result.ok
    assert result.mutating_tool_calls_made == 0


async def test_sohbet_yalan_mutasyonu_duzeltmek_icin_yazmaya_acilmaz(tmp_path, monkeypatch):
    install_provider(monkeypatch, ScriptedProvider([model_result(LIE)] * 4))
    result = await run_agent("bir el at", deps_for(tmp_path, "openai/test"), chat_mode=True)
    assert not result.ok
    assert LIE not in result.final_text
    assert result.mutating_tool_calls_made == 0


@pytest.mark.parametrize(
    "task",
    [
        "Do not start working yet.",
        "Don't start working yet, only discuss the approach.",
        "Start working on explaining recursion.",
        "Önceki işi sadece açıkla: çalışmaya başla demiştim.",
    ],
)
def test_calismaya_basla_alintisi_ve_yasagi_mutasyona_donusmez(task):
    from fusion_cli.engines.agent.action_evidence import task_effect

    assert task_effect(task) is None


@pytest.mark.parametrize(
    "text",
    [
        "İstersen dosyayı güncelleyeceğim.",
        "Henüz değiştirmedim; uygun olunca güncelleyeceğim.",
        "Dün font dosyasını güncelledim.",
        "Önceki turda font dosyasını güncelledim.",
        'Örnek: "Font katmanı eklendi."',
        "```text\nI added the font layer.\n```",
    ],
)
def test_oneri_gecmis_ve_alinti_bu_turun_mutasyonu_sayilmaz(text):
    from fusion_cli.engines.agent.action_evidence import claimed_effects

    assert claimed_effects(text) == ()


async def test_ingilizce_kanitsiz_basari_da_engellenir(tmp_path, monkeypatch):
    lie = "I added the font layer. Everything is complete."
    install_provider(monkeypatch, ScriptedProvider([model_result(lie)] * 4))
    result = await run_agent("bir el at", deps_for(tmp_path, "openai/test"))
    assert not result.ok
    assert lie not in result.final_text


async def test_siniflanmayan_istekte_iddia_yeni_is_emrine_donusmez(tmp_path, monkeypatch):
    provider = ScriptedProvider([model_result(LIE), model_result("Henüz değişiklik yapmadım.")])
    install_provider(monkeypatch, provider)
    result = await run_agent("Bu konu hakkında ne düşünüyorsun?", deps_for(tmp_path, "openai/test"))
    assert result.ok
    assert result.mutating_tool_calls_made == 0
    # Geçersiz iddiayı düzeltmek için kullanıcı adına yeni işlem talep edilmez.
    notes = [message.content for message in result.messages if message.harness_note]
    assert not any("Kullanıcı gerçek bir işlem istedi" in note for note in notes)


@pytest.mark.parametrize(
    "text",
    [
        "I created the following example for you:\n```python\nx = 1\n```",
        "Kod örneğini aşağıda oluşturdum:\n```python\nx = 1\n```",
    ],
)
async def test_sohbette_metin_olarak_teslim_edilen_ornek_mutasyon_degil(
    tmp_path, monkeypatch, text
):
    install_provider(monkeypatch, ScriptedProvider([model_result(text)]))
    result = await run_agent(
        "Örnek bir ifade göster.", deps_for(tmp_path, "openai/test"), chat_mode=True
    )
    assert result.ok
    assert result.final_text == text
    assert result.tool_calls_made == 0


@pytest.mark.parametrize(
    "text",
    [
        "Hangi dosya güncellendi?",
        "Dosya silindi mi?",
        "I created a short poem for you.",
        "Senin için kısa bir şiir oluşturdum.",
    ],
)
async def test_soru_ve_sohbette_uretilen_duzyazi_dosya_islemi_degil(tmp_path, monkeypatch, text):
    install_provider(monkeypatch, ScriptedProvider([model_result(text)]))
    result = await run_agent("Biraz konuşalım.", deps_for(tmp_path, "openai/test"), chat_mode=True)
    assert result.ok
    assert result.final_text == text
    assert result.tool_calls_made == 0


def test_sondaki_kosullu_oneri_onceki_tamamlanma_iddiasini_gizlemez():
    from fusion_cli.engines.agent.action_evidence import claimed_effects

    assert claimed_effects("I updated the files, if you want I can explain the changes.") == (
        "workspace_mutation",
    )


def test_virgul_oncesindeki_kosul_eylemi_nitelemeye_devam_eder():
    from fusion_cli.engines.agent.action_evidence import claimed_effects

    assert claimed_effects("İstersen, dosyayı güncelleyeceğim.") == ()


@pytest.mark.parametrize(
    "text",
    [
        "README.md güncelledim.",
        "`README.md` güncelledim.",
        "`src/worker` güncelledim.",
    ],
)
def test_dosya_adi_ve_yolu_mutasyon_iddiasinin_hedefi_sayilir(text):
    from fusion_cli.engines.agent.action_evidence import claimed_effects

    assert claimed_effects(text) == ("workspace_mutation",)


async def test_model_iki_kez_niyet_yazsa_da_ucuncu_uyaridan_sonra_arac_cagirir(
    tmp_path, monkeypatch
):
    provider = ScriptedProvider(
        [
            model_result(LIE),
            model_result(LIE),
            model_result(tool_calls=[tool_call("write_file", path="font.txt", content="Türkçe")]),
            model_result("font.txt dosyasını güncelledim."),
        ]
    )
    install_provider(monkeypatch, provider)
    result = await run_agent("bir el at", deps_for(tmp_path, "ollama_chat/test"))
    assert result.ok
    assert (tmp_path / "font.txt").read_text() == "Türkçe"
    assert result.mutating_tool_calls_made == 1
