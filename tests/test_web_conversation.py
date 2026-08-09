"""Web sohbet sürekliliği — her turda sıfırdan sohbet açılmaz.

Eskiden her araç turunda `new_chat_url`'e gidilip YENİ bir sohbet açılıyor ve
konuşmanın tamamı tek düz metin bloğu olarak yeniden gönderiliyordu. Model gerçek
bir araç-sonucu protokolü değil "[Önceki araç çağrıları]" başlıklı bir metin
görüyordu; aynı çağrıyı yeniden üretmesi bunun doğal sonucuydu.

Bu dosya sahte bir Playwright yüzeyiyle çalışır: ağ yok, tarayıcı yok.
"""

from __future__ import annotations

import json

import pytest

from fusion_cli.config.models import WebSessionConfig
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


class _FakeContext:
    def __init__(self, log: list[tuple[str, str]]) -> None:
        self._log = log
        self.pages_created = 0

    async def new_page(self) -> _FakePage:
        self.pages_created += 1
        return _FakePage(self._log)


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
    prompt = format_browser_prompt((Message("user", "görev"),))

    assert "FUSION//" in prompt
    assert "başlıkları" in prompt


async def test_transport_cevaptaki_rol_basligini_temizler(pool, monkeypatch):
    async def _send(page, definition, prompt, *, previous="", limit_s=180.0):
        return "### FUSION//SIRADAKİ ADIM\nİş bitti."

    monkeypatch.setattr(web_browser, "_send_turn", _send)
    transport = build_browser_transport(_session(), pool=pool)

    cevap = await transport(WebSessionCredential(), (Message("user", "yap"),), "m")

    assert cevap == "İş bitti."


# --- görev promptun sonunda tekrarlanır ------------------------------------ #
#
# Ölçüldü: sistem promptu + araç sözleşmesi + skill bloğu ~23.500 karakter,
# kullanıcının görevi ~150 karakter. Üstelik görevin ARDINDAN jenerik talimat
# bloğu geliyordu; modelin okuduğu SON şey görev değil kalıp metindi. Gerçek
# koşuda model, görev metninde dosya adı açıkça yazdığı hâlde "herhangi bir
# kullanıcı görevi belirtilmedi" diyerek turu bitirdi.


def test_gorev_promptun_sonunda_tekrarlanir():
    prompt = format_browser_prompt(
        (Message("system", "uzun sistem promptu"), Message("user", "app/page.tsx'i düzenle"))
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
