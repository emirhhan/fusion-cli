"""Web sohbet sürekliliği — her turda sıfırdan sohbet açılmaz.

Eskiden her araç turunda `new_chat_url`'e gidilip YENİ bir sohbet açılıyor ve
konuşmanın tamamı tek düz metin bloğu olarak yeniden gönderiliyordu. Model gerçek
bir araç-sonucu protokolü değil "[Önceki araç çağrıları]" başlıklı bir metin
görüyordu; aynı çağrıyı yeniden üretmesi bunun doğal sonucuydu.

Bu dosya sahte bir Playwright yüzeyiyle çalışır: ağ yok, tarayıcı yok.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from fusion_cli.config.models import WebSessionConfig
from fusion_cli.core.tool_emulation import TOOL_INSTRUCTIONS_LEAD
from fusion_cli.core.types import Message, ToolCall
from fusion_cli.providers import web_browser
from fusion_cli.providers.web_browser import (
    BrowserSessionPool,
    build_browser_transport,
    conversation_digest,
    format_browser_prompt,
)
from fusion_cli.providers.web_session import WebSessionCredential


class _FakePage:
    """Gönderilen prompt'ları kaydeden sahte sayfa."""

    def __init__(self, log: list[tuple[str, str]]) -> None:
        self._log = log
        self.closed = False
        self.goto_count = 0

    async def goto(self, url: str, **kwargs) -> None:
        self.goto_count += 1
        self._log.append(("goto", url))

    async def close(self) -> None:
        self.closed = True

    def is_closed(self) -> bool:
        return self.closed


class _FakeContext:
    def __init__(self, log: list[tuple[str, str]]) -> None:
        self._log = log
        self.pages_created = 0
        self.pages: list[_FakePage] = []

    async def new_page(self) -> _FakePage:
        self.pages_created += 1
        page = _FakePage(self._log)
        self.pages.append(page)
        return page


@pytest.fixture
def log() -> list[tuple[str, str]]:
    return []


@pytest.fixture
def pool(monkeypatch, log) -> BrowserSessionPool:
    manager = BrowserSessionPool()
    context = _FakeContext(log)

    async def _context_for(session, credential):
        return context

    monkeypatch.setattr(manager, "context_for", _context_for)

    async def _open(page, definition):
        await page.goto(definition.new_chat_url)

    sayac = {"n": 0}

    async def _send(page, definition, prompt, *, previous="", limit_s=180.0):
        log.append(("send", prompt))
        # Her tur FARKLI yanıt: gerçek transport tazelik ölçütü olarak önceki
        # yanıtı kullanır; sahtenin de aynı sözleşmeyi karşılaması gerekir.
        sayac["n"] += 1
        return f"tamam-{sayac['n']}"

    monkeypatch.setattr(web_browser, "_open_conversation", _open)
    monkeypatch.setattr(web_browser, "_send_turn", _send)
    manager.fake_context = context  # type: ignore[attr-defined]
    return manager


def _session() -> WebSessionConfig:
    return WebSessionConfig(
        model="chatgpt_web/main/auto",
        provider="chatgpt_web",
        account="main",
        transport="browser",
        tool_support="emulated",
    )


def _messages(count: int) -> tuple[Message, ...]:
    return tuple(Message("user", f"mesaj-{index}") for index in range(count))


async def test_ikinci_tur_yeni_sohbet_acmaz(pool, log):
    transport = build_browser_transport(_session(), pool=pool)
    credential = WebSessionCredential()

    await transport(credential, _messages(2), "chatgpt_web/main/auto")
    await transport(credential, _messages(3), "chatgpt_web/main/auto")

    gotos = [entry for entry in log if entry[0] == "goto"]
    assert len(gotos) == 1, "ikinci tur için yeniden sohbet açılmamalı"
    assert pool.fake_context.pages_created == 1


async def test_secili_web_modeli_gonderimden_once_uygulanir(pool, log, monkeypatch):
    from dataclasses import replace

    selected = replace(_session(), selected_model="Thinking")
    applied: list[str] = []

    async def apply(page, definition, choice):
        applied.append(choice)
        raise web_browser.WebBrowserError("model arayüzünde yok")

    monkeypatch.setattr(web_browser, "ensure_model_choice", apply)
    transport = build_browser_transport(selected, pool=pool)
    with pytest.raises(web_browser.WebBrowserError, match="model arayüzünde yok"):
        await transport(WebSessionCredential(), _messages(2), selected.model)
    assert applied == ["Thinking"]
    assert not [entry for entry in log if entry[0] == "send"]


async def test_havuz_kapatildiktan_sonra_eski_sohbet_sayfasina_devam_etmez(pool, log):
    transport = build_browser_transport(_session(), pool=pool)
    credential = WebSessionCredential()
    await transport(credential, _messages(2), "m")
    await pool.close()
    await transport(credential, _messages(3), "m")
    assert pool.fake_context.pages_created == 2
    assert "mesaj-0" in [entry[1] for entry in log if entry[0] == "send"][-1]


async def test_disaridan_kapanan_sayfayi_yeniden_kullanmaz(pool, log):
    transport = build_browser_transport(_session(), pool=pool)
    credential = WebSessionCredential()
    await transport(credential, _messages(2), "m")
    state = pool.conversation("chatgpt_web", "main", conversation_digest(_messages(1)))
    await state.page.close()
    await transport(credential, _messages(3), "m")
    assert pool.fake_context.pages_created == 2


async def test_ikinci_tur_yalnizca_yeni_mesaji_gonderir(pool, log):
    transport = build_browser_transport(_session(), pool=pool)
    credential = WebSessionCredential()

    await transport(credential, _messages(2), "m")
    await transport(credential, _messages(3), "m")

    gonderilen = [entry[1] for entry in log if entry[0] == "send"]
    assert "mesaj-0" in gonderilen[0] and "mesaj-1" in gonderilen[0]
    # İkinci turda geçmiş yeniden gönderilmez.
    assert "mesaj-2" in gonderilen[1]
    assert "mesaj-0" not in gonderilen[1]
    assert "mesaj-1" not in gonderilen[1]


async def test_gecmis_degisirse_sohbet_sifirlanir(pool, log):
    """Bağlam sıkıştırıldıysa devam etmek modeli yanlış konuşmada bırakırdı."""
    transport = build_browser_transport(_session(), pool=pool)
    credential = WebSessionCredential()

    await transport(credential, _messages(3), "m")
    # Geçmiş yeniden yazıldı: önek artık eşleşmiyor.
    degisen = (Message("user", "bambaşka"), *_messages(3))
    await transport(credential, degisen, "m")

    gotos = [entry for entry in log if entry[0] == "goto"]
    assert len(gotos) == 2, "önek değiştiyse sohbet sıfırlanmalı"
    gonderilen = [entry[1] for entry in log if entry[0] == "send"]
    assert "bambaşka" in gonderilen[1]
    assert "mesaj-0" in gonderilen[1], "sıfırlanan sohbete geçmişin tamamı gider"


async def test_ayni_uzunluktaki_liste_devam_sayilmaz(pool, log):
    """Mesaj eklenmediyse gönderilecek yeni bir şey yoktur; sohbet yeniden kurulur."""
    transport = build_browser_transport(_session(), pool=pool)
    credential = WebSessionCredential()

    await transport(credential, _messages(2), "m")
    await transport(credential, _messages(2), "m")

    assert len([entry for entry in log if entry[0] == "goto"]) == 2


async def test_secici_hatasi_sohbeti_birakir(pool, log, monkeypatch):
    """Sohbet bilinmeyen bir duruma düşerse bırakılır; sonraki tur sıfırdan başlar."""
    transport = build_browser_transport(_session(), pool=pool)
    credential = WebSessionCredential()
    await transport(credential, _messages(2), "m")
    kok = conversation_digest(_messages(2)[:1])
    assert pool.conversation("chatgpt_web", "main", kok) is not None

    cagri = {"sayi": 0}

    async def _patlayan(page, definition, prompt, *, previous="", limit_s=180.0):
        cagri["sayi"] += 1
        raise web_browser.WebBrowserSelectorError("arayüz değişti")

    monkeypatch.setattr(web_browser, "_send_turn", _patlayan)

    with pytest.raises(web_browser.WebBrowserSelectorError):
        await transport(credential, _messages(3), "m")

    assert pool.conversation("chatgpt_web", "main", kok) is None
    assert cagri["sayi"] == 2, "aynı profilde tam olarak bir kez yeniden denenir"


def test_devam_promptu_arac_sonucunu_tasir():
    yeni = format_browser_prompt(
        (Message("tool", "çıktı", name="run_shell", ok=True),), continuation=True
    )
    assert "ARAÇ SONUCU · run_shell · başarılı" in yeni
    assert "çıktı" in yeni


def test_tarayıcı_promptu_gorseli_sessizce_atmaz():
    prompt = format_browser_prompt(
        (
            Message(
                "tool",
                "inceleme",
                name="fixture__inspect",
                ok=True,
                images=("data:image/png;base64,AAA",),
            ),
        ),
        continuation=True,
    )

    assert "görsel içeriği bu web taşımasında desteklenmiyor" in prompt.lower()
    assert "AAA" not in prompt


def test_ozet_rol_ve_icerigi_birlikte_kapsar():
    a = (Message("user", "x"),)
    b = (Message("assistant", "x"),)
    assert conversation_digest(a) != conversation_digest(b)
    assert conversation_digest(a) == conversation_digest((Message("user", "x"),))


# --- Teşhis izi ---------------------------------------------------------------- #
#
# Web modeli araç sonuçlarına tepki vermediğinde ekranda yalnızca araç çağrıları
# görünür; modelin metni taklit araç ayrıştırmasında tüketilir. "Ne gördü, ne
# cevapladı" sorusu başka türlü cevaplanamaz.


async def test_iz_acikken_gonderilen_ve_gelen_kaydedilir(pool, log, tmp_path):
    transport = build_browser_transport(_session(), pool=pool, trace_dir=tmp_path)

    await transport(WebSessionCredential(), _messages(2), "m")

    (dosya,) = list(tmp_path.glob("*.jsonl"))
    kayit = json.loads(dosya.read_text(encoding="utf-8").strip())
    assert "mesaj-0" in kayit["gonderilen"]
    assert kayit["gelen"].startswith("tamam")
    assert kayit["devam"] is False


async def test_iz_kapaliyken_hicbir_sey_yazilmaz(pool, log, tmp_path):
    transport = build_browser_transport(_session(), pool=pool, trace_dir=None)

    await transport(WebSessionCredential(), _messages(2), "m")

    assert list(tmp_path.iterdir()) == []


async def test_devam_turu_iz_kaydinda_isaretlenir(pool, log, tmp_path):
    transport = build_browser_transport(_session(), pool=pool, trace_dir=tmp_path)
    credential = WebSessionCredential()

    await transport(credential, _messages(2), "m")
    await transport(credential, _messages(3), "m")

    (dosya,) = list(tmp_path.glob("*.jsonl"))
    kayitlar = [json.loads(satir) for satir in dosya.read_text(encoding="utf-8").splitlines()]
    assert [kayit["devam"] for kayit in kayitlar] == [False, True]
    # Devam turunda YALNIZCA yeni mesaj gönderilmiş olmalı.
    assert "mesaj-0" not in kayitlar[1]["gonderilen"]


# --- Devam turunda ASİSTAN mesajı gönderilmez --------------------------------- #
#
# Gerçek koşu (Gemini web, iz kaydı): üç dosya okundu, sonuçlar döndü, ardından model
# AYNI üç okumayı yeniden istedi ve tekrar kapısı turu kesti. Sebep, sohbet açıkken
# modelin KENDİ turunun ona geri gönderilmesiydi: kendi araç çağrılarını yeni bir
# istek gibi görüp aynen tekrar üretiyordu.


def test_devam_turunda_asistan_mesaji_geri_gonderilmez():
    mesajlar = (
        Message(
            "assistant",
            "",
            tool_calls=(ToolCall(id="1", name="read_file", arguments='{"path":"a.py"}'),),
        ),
        Message("tool", "dosya içeriği", tool_call_id="1", name="read_file", ok=True),
    )

    prompt = format_browser_prompt(mesajlar, continuation=True)

    assert "ASİSTAN" not in prompt
    assert "[Önceki araç çağrıları]" not in prompt
    assert "dosya içeriği" in prompt


def test_yeni_sohbette_asistan_mesaji_korunur():
    """Sohbet sıfırlandığında geçmişin tamamı gerekir; asistan turu da dahil."""
    mesajlar = (
        Message("user", "oku"),
        Message(
            "assistant",
            "",
            tool_calls=(ToolCall(id="1", name="read_file", arguments='{"path":"a.py"}'),),
        ),
        Message("tool", "dosya içeriği", tool_call_id="1", name="read_file", ok=True),
    )

    prompt = format_browser_prompt(mesajlar, continuation=False)

    assert "### FUSION//ASİSTAN" in prompt
    assert "[Önceki araç çağrıları]" in prompt


def test_arac_sonucu_hangi_cagriya_ait_oldugunu_soyler():
    """Üç sonucun da aynı başlıkla gelmesi modelin ayırt etmesini imkânsız kılıyordu."""
    cagrilar = tuple(
        ToolCall(id=str(i), name="read_file", arguments=f'{{"path":"dosya{i}.py"}}')
        for i in range(3)
    )
    mesajlar = (
        Message("assistant", "", tool_calls=cagrilar),
        *[
            Message("tool", f"içerik-{i}", tool_call_id=str(i), name="read_file", ok=True)
            for i in range(3)
        ],
    )

    prompt = format_browser_prompt(mesajlar, continuation=True)

    for i in range(3):
        assert f"dosya{i}.py" in prompt


def test_devam_talimati_en_basta_durur():
    """A/B ölçüldü: talimat dosya içeriğinin ardına düşünce model onu kaybediyordu."""
    prompt = format_browser_prompt(
        (Message("tool", "x" * 3000, name="read_file", ok=True),), continuation=True
    )

    assert prompt.startswith("### FUSION//SIRADAKİ ADIM")
    assert "ZATEN yaptın" in prompt


def test_arac_sonucu_basligi_cagri_bicimine_benzemez():
    """`read_file {"path": "x.py"}` bir araç çağrısı gibi görünüyor ve taklit ediliyordu."""
    mesajlar = (
        Message(
            "assistant",
            "",
            tool_calls=(ToolCall(id="1", name="read_file", arguments='{"path":"envanter.py"}'),),
        ),
        Message("tool", "içerik", tool_call_id="1", name="read_file", ok=True),
    )

    prompt = format_browser_prompt(mesajlar, continuation=True)

    assert "read_file · envanter.py" in prompt, "dosya adı korunmalı"
    assert '{"path"' not in prompt, "ham JSON çağrı biçimine benziyor"


# --- Yardımcı çağrılar ana sohbeti düşürmez ----------------------------------- #
#
# İzde görüldü: agent turunun ardından ders çıkarımı çağrısı sohbeti sıfırlıyor
# (devam=False) ve sonraki tur geçmişin tamamını yeniden göndermek zorunda kalıyordu.
# Sebep, sohbetin yalnızca (sağlayıcı, hesap) ile anahtarlanmasıydı.


async def test_farkli_kok_ayri_sohbet_alir(pool, log):
    transport = build_browser_transport(_session(), pool=pool)
    credential = WebSessionCredential()

    ana = (Message("system", "agent sistem promptu"), Message("user", "görev"))
    yardimci = (Message("system", "ders çıkar"), Message("user", "özetle"))

    await transport(credential, ana, "m")
    await transport(credential, yardimci, "m")
    # Ana sohbet HÂLÂ açık olmalı: yardımcı çağrı onu düşürmemeli.
    await transport(credential, (*ana, Message("user", "devam")), "m")

    gonderilen = [entry[1] for entry in log if entry[0] == "send"]
    assert "devam" in gonderilen[2]
    assert "agent sistem promptu" not in gonderilen[2], "ana sohbet korunmalıydı"


async def test_ayni_kok_sohbeti_paylasir(pool, log):
    transport = build_browser_transport(_session(), pool=pool)
    credential = WebSessionCredential()
    ana = (Message("system", "kök"), Message("user", "bir"))

    await transport(credential, ana, "m")
    await transport(credential, (*ana, Message("user", "iki")), "m")

    assert len([e for e in log if e[0] == "goto"]) == 1


# --- rol başlığı sızıntısı ------------------------------------------------- #
#
# Gözlemlendi (Gemini web): model nihai cevabına `FUSION//SONRAKİ ADIM` başlığıyla
# başladı. Bu başlık modelin uydurması değil, taşıma çerçevesinin taklididir —
# `format_browser_prompt` her bloğu `### FUSION//…` ile etiketler. Model çerçeveyi
# içerik sanıp benimseyince kendini "sıradaki adımı sor" rolünde gördü ve görevi
# yapmak yerine kullanıcıya ne yapması gerektiğini sordu.


def test_rol_basligi_cevaptan_ayiklanir():
    cevap = "### FUSION//SIRADAKİ ADIM\nDizin yapısı incelendi.\n\nDevam ediyorum."

    assert web_browser.strip_role_headers(cevap) == "Dizin yapısı incelendi.\n\nDevam ediyorum."


def test_govdedeki_rol_basligi_da_ayiklanir():
    cevap = "Önce şunu yaptım.\n\nFUSION//KULLANICI\nSonra bunu."

    assert web_browser.strip_role_headers(cevap) == "Önce şunu yaptım.\n\nSonra bunu."


def test_normal_markdown_basligi_korunur():
    """Ayıklama YALNIZCA rol önekine bakar; modelin kendi başlıkları kalır."""
    cevap = "### Yapılanlar\nüç dosya güncellendi"

    assert web_browser.strip_role_headers(cevap) == cevap


def test_prompt_rol_basligini_tekrarlamamayi_soyler():
    prompt = format_browser_prompt(
        (Message("system", TOOL_INSTRUCTIONS_LEAD), Message("user", "görev"))
    )

    assert "FUSION//" in prompt
    assert "başlıkları" in prompt


def test_aracsiz_tek_soru_arac_cercevesi_olmadan_gider():
    """Ölçüldü (2 Ekim 2026, Gemini web "Pro"): öğretmen sorusuna "yeni bir araç çağır,
    todo_write ile plan yaz" talimatı ekleniyordu; model kalıp ret veriyordu."""
    soru = "WordPress temasında zorunlu iki dosya hangileridir?"

    prompt = format_browser_prompt((Message("user", soru),))

    assert prompt == soru


def test_aracsiz_sistemli_istekte_arac_talimati_yok():
    prompt = format_browser_prompt(
        (Message("system", "Sen bir hakemsin."), Message("user", "Hangisi doğru?"))
    )

    assert "Sen bir hakemsin." in prompt
    assert prompt.rstrip().endswith("Hangisi doğru?")
    assert "todo_write" not in prompt
    assert "araç çağır" not in prompt


async def test_transport_cevaptaki_rol_basligini_temizler(pool, monkeypatch):
    async def _send(page, definition, prompt, *, previous="", limit_s=180.0):
        return "### FUSION//SIRADAKİ ADIM\nİş bitti."

    monkeypatch.setattr(web_browser, "_send_turn", _send)
    transport = build_browser_transport(_session(), pool=pool)

    cevap = await transport(WebSessionCredential(), (Message("user", "yap"),), "m")

    assert cevap.text == "İş bitti."


# --- görev promptun sonunda tekrarlanır ------------------------------------ #
#
# Ölçüldü: sistem promptu + araç sözleşmesi + skill bloğu ~23.500 karakter,
# kullanıcının görevi ~150 karakter. Üstelik görevin ARDINDAN jenerik talimat
# bloğu geliyordu; modelin okuduğu SON şey görev değil kalıp metindi. Gerçek
# koşuda model, görev metninde dosya adı açıkça yazdığı hâlde "herhangi bir
# kullanıcı görevi belirtilmedi" diyerek turu bitirdi.


def test_gorev_promptun_sonunda_tekrarlanir():
    prompt = format_browser_prompt(
        (
            Message("system", f"uzun sistem promptu\n{TOOL_INSTRUCTIONS_LEAD}"),
            Message("user", "app/page.tsx'i düzenle"),
        )
    )

    assert prompt.rstrip().endswith("app/page.tsx'i düzenle")
    assert "GÖREV (yapılacak iş budur)" in prompt


def test_devam_turunda_da_gorev_sonda_durur():
    prompt = format_browser_prompt(
        (Message("user", "devam et"), Message("tool", "çıktı", name="run_shell", ok=True)),
        continuation=True,
    )

    assert prompt.rstrip().endswith("devam et")


def test_kullanici_mesaji_yoksa_hatirlatma_eklenmez():
    prompt = format_browser_prompt((Message("tool", "x", name="read_file", ok=True),))

    assert "GÖREV (yapılacak iş budur)" not in prompt


# --- sayfadan sızan atıf satırları ----------------------------------------- #
#
# Ölçüldü, iki ayrı canlı koşuda: cevabın sonuna "COGNOiSe.com - The IBM Cognos
# Community" ve "erlas.com.tr" düştü. İkisi de modelin cümlesi değil, Gemini
# sayfasındaki kaynak rozetinin metni.


def test_ciplak_alan_adi_satiri_ayiklanir():
    cevap = "Değişiklik tamamlandı.\nerlas.com.tr"

    assert web_browser.strip_role_headers(cevap) == "Değişiklik tamamlandı."


def test_aciklamali_kaynak_satiri_da_ayiklanir():
    cevap = "Panel güncellendi.\nCOGNOiSe.com - The IBM Cognos Community"

    assert web_browser.strip_role_headers(cevap) == "Panel güncellendi."


def test_cumle_icindeki_alan_adi_korunur():
    cevap = "Ayrıntı için example.com adresine bakabilirsin."

    assert web_browser.strip_role_headers(cevap) == cevap


def test_dosya_adi_satiri_yanlislikla_ayiklanmaz():
    """`app/page.tsx` alan adına benzemez; korunmalı."""
    cevap = "Değişen dosya:\napp/page.tsx"

    assert "app/page.tsx" in web_browser.strip_role_headers(cevap)


# --- seçili model kalıp ret verirse komşu modele geçilir -------------------- #
#
# Ölçüldü (2 Ekim 2026, Gemini web Plus hesabı): "3.1 Pro" seçiliyken her soruya
# 85-340 sn sonra "Ben yalnızca bir dil modeliyim…" geldi; "3.6 Flash" 25 sn'de
# doğru cevapladı. Öğretmen hiçbir plan sorusunu cevaplayamıyordu.

_RET = "Ben bir dil modeliyim ve isteğinizi gerçekleştirebilecek şekilde tasarlanmadım."


def _secili(model: str) -> WebSessionConfig:
    return WebSessionConfig(
        model="gemini_web/main/auto",
        provider="gemini_web",
        account="main",
        transport="browser",
        tool_support="emulated",
        selected_model=model,
    )


def _kalip_ret_ortami(monkeypatch, cevaplar: dict[str, str]) -> dict[str, list[str]]:
    """Seçili modele göre cevap veren sahte sayfa; seçimleri ve gönderimleri kaydeder."""
    kayit: dict[str, list[str]] = {"secim": [], "gonderim": []}
    durum = {"model": ""}

    async def _ensure(page, definition, choice):
        durum["model"] = choice
        kayit["secim"].append(choice)
        return choice

    async def _switch(page, definition, current):
        komsu = "3.6 Flash" if current == "3.1 Pro" else ""
        if komsu:
            durum["model"] = komsu
        return komsu

    async def _send(page, definition, prompt, *, previous="", limit_s=180.0):
        kayit["gonderim"].append(durum["model"])
        return cevaplar[durum["model"]]

    async def _tier(page, definition):
        return durum["model"].split()[-1] if durum["model"] else ""

    monkeypatch.setattr(web_browser, "ensure_model_choice", _ensure)
    monkeypatch.setattr(web_browser, "switch_to_adjacent_model", _switch)
    monkeypatch.setattr(web_browser, "_send_turn", _send)
    monkeypatch.setattr(web_browser, "observed_tier", _tier)
    return kayit


async def test_secili_model_kalip_ret_verirse_komsu_modelle_yeniden_sorulur(pool, monkeypatch):
    kayit = _kalip_ret_ortami(monkeypatch, {"3.1 Pro": _RET, "3.6 Flash": "index.php ve style.css"})
    transport = build_browser_transport(_secili("3.1 Pro"), pool=pool)

    cevap = await transport(WebSessionCredential(), (Message("user", "soru"),), "m")

    assert cevap.text == "index.php ve style.css"
    assert cevap.tier == "Flash"
    assert kayit["gonderim"] == ["3.1 Pro", "3.6 Flash"]


async def test_kalip_ret_sonrasi_yeni_sohbet_dogrudan_calisan_modelle_acilir(pool, monkeypatch):
    kayit = _kalip_ret_ortami(monkeypatch, {"3.1 Pro": _RET, "3.6 Flash": "cevap"})
    transport = build_browser_transport(_secili("3.1 Pro"), pool=pool)
    await transport(WebSessionCredential(), (Message("user", "ilk soru"),), "m")
    kayit["gonderim"].clear()

    await transport(WebSessionCredential(), (Message("user", "başka soru"),), "m")

    # İkinci sohbet reddi yeniden beklemez: doğrudan çalışan modelle gönderilir.
    assert kayit["gonderim"] == ["3.6 Flash"]


async def test_komsu_model_de_reddederse_ret_oldugu_gibi_doner(pool, monkeypatch):
    kayit = _kalip_ret_ortami(monkeypatch, {"3.1 Pro": _RET, "3.6 Flash": _RET})
    transport = build_browser_transport(_secili("3.1 Pro"), pool=pool)

    cevap = await transport(WebSessionCredential(), (Message("user", "soru"),), "m")

    assert cevap.text == _RET
    # Kullanıcının seçimine geri dönülür ve yedek HATIRLANMAZ.
    assert kayit["secim"][-1] == "3.1 Pro"
    assert pool.model_choice(_secili("3.1 Pro")) == "3.1 Pro"


async def test_model_secilmemisse_kalip_ret_yeniden_sorulmaz(pool, monkeypatch):
    kayit = _kalip_ret_ortami(monkeypatch, {"": _RET})
    transport = build_browser_transport(_secili(""), pool=pool)

    cevap = await transport(WebSessionCredential(), (Message("user", "soru"),), "m")

    assert cevap.text == _RET
    assert kayit["gonderim"] == [""]


async def test_sure_asan_secili_modelden_sonraki_deneme_komsu_modelle_yapilir(pool, monkeypatch):
    """Ölçüldü (2 Ekim 2026): "3.1 Pro" plan sorusunda 180 sn sınırını üç denemede de
    aştı (546 sn); aynı modeli üç kez beklemek yerine ikinci deneme komşuyla yapılır."""
    kayit = _kalip_ret_ortami(monkeypatch, {"3.1 Pro": "geç cevap", "3.6 Flash": "plan"})
    asil_gonder = web_browser._send_turn

    async def _yavas(page, definition, prompt, *, previous="", limit_s=180.0):
        if kayit["secim"][-1:] == ["3.1 Pro"] and not kayit["gonderim"]:
            kayit["gonderim"].append("3.1 Pro")
            await asyncio.sleep(60)
        return await asil_gonder(page, definition, prompt, previous=previous, limit_s=limit_s)

    monkeypatch.setattr(web_browser, "_send_turn", _yavas)
    monkeypatch.setattr(web_browser, "MIN_BROWSER_TURN_S", 0.05)
    oturum = _secili("3.1 Pro")
    transport = build_browser_transport(oturum, pool=pool, timeout_s=0.05)

    with pytest.raises(web_browser.WebBrowserError, match="tamamlanmadı"):
        await transport(WebSessionCredential(), (Message("user", "plan ver"),), "m")
    cevap = await transport(WebSessionCredential(), (Message("user", "plan ver"),), "m")

    assert cevap.text == "plan" and cevap.tier == "Flash"
    assert pool.model_choice(oturum) == "3.6 Flash"


async def test_sure_asan_yeni_sohbetin_sayfasi_acik_birakilmaz(pool, monkeypatch):
    """Ölçüldü (2 Ekim 2026): süresi dolan iki tur, paylaşılan Chrome'da hâlâ cevap
    üreten iki sahipsiz sekme bıraktı (sohbet havuza kaydedilmeden iptal ediliyordu)."""

    async def _yavas(page, definition, prompt, *, previous="", limit_s=180.0):
        await asyncio.sleep(60)

    monkeypatch.setattr(web_browser, "_send_turn", _yavas)
    monkeypatch.setattr(web_browser, "MIN_BROWSER_TURN_S", 0.05)
    transport = build_browser_transport(_session(), pool=pool, timeout_s=0.05)

    with pytest.raises(web_browser.WebBrowserError, match="tamamlanmadı"):
        await transport(WebSessionCredential(), (Message("user", "soru"),), "m")

    assert all(page.is_closed() for page in pool.fake_context.pages)  # type: ignore[attr-defined]


# --- insan doğrulaması: pencere açılır, kullanıcı çözer, tur sürer ---------------- #
#
# Fusion captcha'yı AŞMAZ. Ölçüldü (2 Ekim 2026): ChatGPT oturumu günlerce doğrulama
# bekledi; her tur "fusion web-login çalıştır" diyerek düştü ve öğretmen yedeği hiç çalışmadı.

_DOGRULAMA = web_browser.WebBrowserAuthError(
    "authentication: ChatGPT insan doğrulaması (captcha) istiyor. [sayfa işareti: just a moment]"
)


class _SahteTarayici:
    def __init__(self, gosterebilir: bool = True) -> None:
        self.gosterebilir = gosterebilir
        self.notlar: list[str] = []
        self.yeniden_gizlendi = 0

    async def reveal_window(self, notice: str) -> bool:
        self.notlar.append(notice)
        return self.gosterebilir

    async def reassert_window(self, *, headless) -> None:
        self.yeniden_gizlendi += 1


async def test_insan_dogrulamasinda_pencere_acilir_ve_cozulunce_adim_yinelenir(pool, monkeypatch):
    tarayici = _SahteTarayici()
    monkeypatch.setattr(web_browser, "_shared_profile_browser", lambda *_a: tarayici)
    monkeypatch.setattr(web_browser, "HUMAN_VERIFY_POLL_S", 0.0)
    temiz = {"n": 0}

    async def _temizlendi(page, definition, wait_s):
        temiz["n"] += 1
        return True

    monkeypatch.setattr(web_browser, "_wait_until_challenge_clears", _temizlendi)
    acilis: list[int] = []

    async def _ac(page, definition):
        acilis.append(1)
        if len(acilis) == 1:
            raise _DOGRULAMA

    monkeypatch.setattr(web_browser, "_open_ready_conversation", _ac)
    transport = build_browser_transport(_session(), pool=pool)

    cevap = await transport(WebSessionCredential(), (Message("user", "yap"),), "m")

    assert cevap.text.startswith("tamam-")
    assert acilis == [1, 1] and temiz["n"] == 1
    assert "insan doğrulaması istiyor: açılan Chrome penceresinde" in tarayici.notlar[0]
    assert tarayici.yeniden_gizlendi >= 1  # yeni sekme + doğrulama sonrası


async def test_dogrulama_suresinde_cozulmezse_ayni_hata_doner(pool, monkeypatch):
    tarayici = _SahteTarayici()
    monkeypatch.setattr(web_browser, "_shared_profile_browser", lambda *_a: tarayici)

    async def _temizlenmedi(page, definition, wait_s):
        return False

    monkeypatch.setattr(web_browser, "_wait_until_challenge_clears", _temizlenmedi)

    async def _ac(page, definition):
        raise _DOGRULAMA

    monkeypatch.setattr(web_browser, "_open_ready_conversation", _ac)
    transport = build_browser_transport(_session(), pool=pool)

    with pytest.raises(web_browser.WebBrowserAuthError, match="insan doğrulaması"):
        await transport(WebSessionCredential(), (Message("user", "yap"),), "m")
    assert tarayici.yeniden_gizlendi >= 1  # yeni sekme + doğrulama sonrası


async def test_gorunmez_kipte_pencere_acilamazsa_beklenmez(pool, monkeypatch):
    tarayici = _SahteTarayici(gosterebilir=False)
    monkeypatch.setattr(web_browser, "_shared_profile_browser", lambda *_a: tarayici)
    beklendi = {"n": 0}

    async def _bekle(page, definition, wait_s):
        beklendi["n"] += 1
        return True

    monkeypatch.setattr(web_browser, "_wait_until_challenge_clears", _bekle)

    async def _ac(page, definition):
        raise _DOGRULAMA

    monkeypatch.setattr(web_browser, "_open_ready_conversation", _ac)
    transport = build_browser_transport(_session(), pool=pool)

    with pytest.raises(web_browser.WebBrowserAuthError):
        await transport(WebSessionCredential(), (Message("user", "yap"),), "m")
    assert beklendi["n"] == 0
