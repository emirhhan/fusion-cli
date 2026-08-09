"""Tarayıcı tabanlı sağlayıcılar — kullanıcının KENDİ web AI aboneliği.

Buradaki adaptörler ikinci bir yönlendirici uygulamaya bağlı değildir: Fusion'ın
sahip olduğu izole bir Playwright profili kullanılır, sağlayıcının normal web
arayüzü açılır ve Fusion'ın kanonik mesaj/araç protokolü bir tarayıcı sohbetine
çevrilir.

Güvenlik ve kapsam sınırı:
- Kullanıcının NORMAL tarayıcı profili hiçbir koşulda okunmaz.
- Kullanıcı ya Fusion'ın izole profilinde AÇIKÇA oturum açar ya da kendi Cookie
  başlığını kontrol panelinden verir.
- CAPTCHA çözme, gizlenme eklentisi, parmak izi taklidi ve anti-bot atlatma YOKTUR.
- Cookie yalnızca şifreli Fusion sır deposunda durur ve hata metinlerinden ayıklanır.

Web arayüzleri sık değişir. Bu yüzden her sağlayıcı için birden çok seçici tanımlıdır
ve her arıza, sonsuza kadar beklemek yerine eyleme dönüştürülebilir bir oturum/seçici
hatası olarak bildirilir.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config.models import WebSessionConfig
from ..config.paths import user_data_dir
from ..core.constants import MIN_BROWSER_TURN_S
from ..core.redaction import redact
from ..core.types import Message, ToolCall
from .web_session import WebSessionCredential, WebTransport

#: Rol başlıklarının ÖNEKİ. Çıplak `### SİSTEM` yeterli değildi: sistem promptuna
#: enjekte edilen skill metinleri de Markdown başlığı taşıyor (`### Typed Error
#: Classes`, `### Result Pattern`…) ve izde bunlar bizim rol başlıklarımızla aynı
#: düzeyde görünüyordu. Model hangisinin çerçeve hangisinin içerik olduğunu
#: ayırt edemiyordu.
#: Tarayıcıdan yanıt beklerken varsayılan üst sınır.
#
# Bu değer eskiden `_wait_for_response` içine gömülüydü ve turun bütçesini HİÇ
# tanımıyordu: `_transport` doğru sınırı hesaplıyor ama aşağıya geçirmiyordu.
# Sonuç ölçüldü — her deneme 180 sn bekleyebiliyor, iki deneme 360 sn ediyor ve
# 36 model çağrılık bir tur saatlerce sürebiliyordu. Sınır artık çağrı başına
# geçirilir; bu sabit yalnızca doğrudan çağrılar için yedektir.
DEFAULT_RESPONSE_WAIT_S = 180.0

ROLE_PREFIX = "FUSION//"

#: Modelin cevabında taklit ettiği rol başlığı satırı.
#:
#: Gözlemlendi (Gemini web): model nihai cevabına `FUSION//SONRAKİ ADIM` başlığıyla
#: başladı. Başlık modelin uydurması değil, taşıma çerçevesinin taklididir. Zararı
#: kozmetik değil: çerçeveyi içerik sanan model kendini "sıradaki adımı sor"
#: rolünde görüyor ve görevi yapmak yerine kullanıcıya ne yapacağını soruyor.
#:
#: Ayıklama YALNIZCA önekle eşleşen satırı düşürür; modelin kendi Markdown
#: başlıkları (`### Yapılanlar`) korunur.
_ROLE_HEADER_LINE = re.compile(rf"^[ \t]*#{{0,6}}[ \t]*{re.escape(ROLE_PREFIX)}.*$", re.MULTILINE)


def strip_role_headers(answer: str) -> str:
    """Modelin cevabına sızmış taşıma rol başlıklarını temizle."""
    return _clean_text(_ROLE_HEADER_LINE.sub("", answer))


class WebBrowserError(RuntimeError):
    """Tarayıcı tabanlı web sağlayıcılarının kök hatası."""


class WebBrowserAuthError(WebBrowserError):
    """İzole tarayıcı profilinde oturum açık değil ya da süresi dolmuş."""


class WebBrowserSelectorError(WebBrowserError):
    """Sağlayıcı arayüzü değişti; tanımlı seçiciler artık eşleşmiyor."""


@dataclass(frozen=True, slots=True)
class BrowserProviderDefinition:
    id: str
    name: str
    home_url: str
    new_chat_url: str
    cookie_urls: tuple[str, ...]
    input_selectors: tuple[str, ...]
    send_selectors: tuple[str, ...]
    response_selectors: tuple[str, ...]
    stop_selectors: tuple[str, ...]
    login_markers: tuple[str, ...]
    #: SOHBET alanının tamamı: kullanıcı turları + model turları + geçmiş.
    #
    # Sınıflandırma (oturum/captcha/kota) bu alana ASLA bakmaz. Sebep ölçüldü:
    # Fusion sistem promptunu sohbete yazıyor ve sohbet SÜRDÜĞÜ için önceki
    # turların promptu ekranda kalıyor. Prompta "insan doğrulaması (CAPTCHA)"
    # cümlesi eklendiğinde Fusion kendi geçmişini okuyup her turu "captcha
    # istiyor" diye düşürdü; kullanıcı gerçekten giriş yapmış olmasına rağmen.
    #
    # `response_selectors` yetmiyordu: yalnızca MODEL turlarını kapsıyor,
    # kullanıcı turlarını (yani bizim promptlarımızı) değil.
    history_selectors: tuple[str, ...] = ()
    default_models: tuple[str, ...] = ("auto",)
    cookie_hint: str = "Tam Cookie başlığı"


WEB_BROWSER_PROVIDERS: dict[str, BrowserProviderDefinition] = {
    "chatgpt_web": BrowserProviderDefinition(
        id="chatgpt_web",
        name="ChatGPT Web (Plus/Pro)",
        home_url="https://chatgpt.com/",
        new_chat_url="https://chatgpt.com/",
        cookie_urls=("https://chatgpt.com/", "https://openai.com/"),
        input_selectors=(
            "#prompt-textarea",
            '[data-testid="prompt-textarea"]',
            'div[contenteditable="true"][data-lexical-editor="true"]',
            'textarea[placeholder*="Message"]',
            "textarea",
        ),
        send_selectors=(
            'button[data-testid="send-button"]',
            'button[aria-label*="Send"]',
            'button[aria-label*="Gönder"]',
        ),
        # Sıra dardan genişe: `article[data-testid^="conversation-turn-"]` tüm turu
        # (kullanıcı mesajı, eylem düğmeleri) kapsayan geniş kaptır, en sonda.
        response_selectors=(
            '[data-testid^="conversation-turn-"] [data-message-author-role="assistant"]',
            '[data-message-author-role="assistant"]',
            'article[data-testid^="conversation-turn-"]',
        ),
        stop_selectors=(
            'button[data-testid="stop-button"]',
            'button[aria-label*="Stop"]',
            'button[aria-label*="Durdur"]',
        ),
        login_markers=("log in", "sign up", "giriş yap", "oturum aç"),
        history_selectors=(
            "[data-message-author-role]",
            'article[data-testid^="conversation-turn-"]',
            "main .group\\/conversation-turn",
        ),
        default_models=("auto",),
        cookie_hint="chatgpt.com üzerindeki oturum açmış bir isteğin tam Cookie başlığı",
    ),
    "claude_web": BrowserProviderDefinition(
        id="claude_web",
        name="Claude Web (Pro/Max)",
        home_url="https://claude.ai/",
        new_chat_url="https://claude.ai/new",
        cookie_urls=("https://claude.ai/",),
        input_selectors=(
            'div.ProseMirror[contenteditable="true"]',
            '[contenteditable="true"][data-placeholder]',
            'fieldset [contenteditable="true"]',
            "textarea",
        ),
        send_selectors=(
            'button[aria-label*="Send"]',
            'button[aria-label*="Gönder"]',
            'button[data-testid*="send"]',
        ),
        response_selectors=(
            '[data-testid="assistant-message"]',
            "[data-is-streaming] .font-claude-message",
            ".font-claude-message",
            'div[data-testid^="message-"]',
        ),
        stop_selectors=(
            'button[aria-label*="Stop"]',
            'button[aria-label*="Durdur"]',
        ),
        login_markers=("log in", "continue with google", "giriş yap", "oturum aç"),
        history_selectors=(
            '[data-testid="user-message"]',
            '[data-testid="assistant-message"]',
            ".font-claude-message",
            "div[data-test-render-count]",
        ),
        default_models=("auto",),
        cookie_hint="claude.ai oturumunun tam Cookie başlığı (sessionKey dahil)",
    ),
    "gemini_web": BrowserProviderDefinition(
        id="gemini_web",
        name="Gemini Web (Google AI Pro/Ultra)",
        home_url="https://gemini.google.com/app",
        new_chat_url="https://gemini.google.com/app",
        cookie_urls=("https://gemini.google.com/", "https://accounts.google.com/"),
        input_selectors=(
            'rich-textarea div[contenteditable="true"]',
            'div[contenteditable="true"][aria-label]',
            "textarea[aria-label]",
            "textarea",
        ),
        send_selectors=(
            'button[aria-label*="Send"]',
            'button[aria-label*="Gönder"]',
            "button.send-button",
        ),
        # Sıra DARDAN GENİŞE: ilk sonuç veren kazanır (bkz. `_response_snapshot`).
        # `model-response` kaynak/atıf kartlarını da içeren geniş kaptır ve en
        # sona alınmıştır; yalnızca dar seçiciler arayüz değişikliğiyle
        # eşleşmediğinde devreye girer.
        response_selectors=(
            "model-response .model-response-text",
            ".model-response-text",
            '[data-test-id="response"]',
            "model-response",
        ),
        stop_selectors=(
            'button[aria-label*="Stop"]',
            'button[aria-label*="Durdur"]',
        ),
        login_markers=("sign in", "oturum aç", "giriş yap", "choose an account"),
        history_selectors=(
            "user-query",
            "model-response",
            ".conversation-container",
            "infinite-scroller",
        ),
        default_models=("auto",),
        cookie_hint=(
            "gemini.google.com isteğinin tam Cookie başlığı; Google için tarayıcıyla giriş önerilir"
        ),
    ),
    "copilot_web": BrowserProviderDefinition(
        id="copilot_web",
        name="Microsoft Copilot Web",
        home_url="https://copilot.microsoft.com/",
        new_chat_url="https://copilot.microsoft.com/",
        cookie_urls=(
            "https://copilot.microsoft.com/",
            "https://login.live.com/",
            "https://www.bing.com/",
        ),
        input_selectors=(
            "textarea[placeholder]",
            "textarea[aria-label]",
            'div[contenteditable="true"]',
            "textarea",
        ),
        send_selectors=(
            'button[aria-label*="Submit"]',
            'button[aria-label*="Send"]',
            'button[aria-label*="Gönder"]',
        ),
        response_selectors=(
            '[data-content="ai-message"]',
            '[data-testid="copilot-response"]',
            ".ac-textBlock",
            'cib-message-group[source="bot"]',
        ),
        stop_selectors=(
            'button[aria-label*="Stop"]',
            'button[aria-label*="Durdur"]',
        ),
        login_markers=("sign in", "oturum aç", "giriş yap", "microsoft account"),
        history_selectors=(
            '[data-content="ai-message"]',
            '[data-content="user-message"]',
            "cib-message-group",
            '[data-testid="chat-turn"]',
        ),
        default_models=("auto",),
        cookie_hint=(
            "copilot.microsoft.com oturumundaki tam Cookie başlığı; tarayıcıyla giriş önerilir"
        ),
    ),
}


def normalize_account(account: str) -> str:
    """Kullanıcının yazdığı hesap etiketini model kimliği/yol/HTML için normalize et."""
    return _slug(account)


def browser_profile_dir(provider: str, account: str) -> Path:
    """Bir sağlayıcı hesabı için kararlı ve İZOLE profil dizinini döndür.

    Kullanıcının normal tarayıcı profili HİÇBİR koşulda okunmaz; Fusion yalnızca
    kendi dizinini kullanır.
    """
    safe_provider = _slug(provider)
    safe_account = normalize_account(account)
    return user_data_dir() / "web_profiles" / safe_provider / safe_account


# Chrome, çökme veya zorla kapatma sonrası profil kökünde bu tekil-örnek (singleton)
# işaretlerini geride bırakır.  Bir sonraki başlatmada bunları canlı bir oturum sanıp
# URL'i ölü sokete devredip hemen kapanır — Playwright bunu TargetClosedError olarak görür.
_SINGLETON_LOCK_NAMES = ("SingletonLock", "SingletonCookie", "SingletonSocket")


def clear_profile_singletons(profile: Path) -> None:
    """Bir önceki çalıştırmadan kalan Chrome tekil-örnek kilitlerini temizle.

    Bu kilitler temizlenmezse görünür giriş tarayıcısı açılır açılmaz kapanır.  İşaretler
    Chrome tarafından her başlatmada yeniden oluşturulur; silinmeleri güvenlidir.
    """
    for name in _SINGLETON_LOCK_NAMES:
        lock = profile / name
        # Bunlar genelde sembolik bağlantıdır; hedef var olmasa bile bağlantı silinmelidir.
        with contextlib.suppress(FileNotFoundError, OSError):
            if lock.is_symlink() or lock.exists():
                lock.unlink()


def web_secret_name(provider: str, account: str) -> str:
    """Encrypted-store key for a raw Cookie header.  Not an environment variable."""
    return f"WEB_SECRET::{_slug(provider)}::{normalize_account(account)}"


def provider_definition(provider: str) -> BrowserProviderDefinition:
    try:
        return WEB_BROWSER_PROVIDERS[provider]
    except KeyError as error:
        raise WebBrowserError(f"tanınmayan web sağlayıcısı: {provider}") from error


def parse_cookie_header(raw: str) -> dict[str, str]:
    """Cookie başlığını, içinde '=' geçen değerleri bozmadan ayrıştır."""
    cookies: dict[str, str] = {}
    for part in raw.split(";"):
        item = part.strip()
        if not item or "=" not in item:
            continue
        name, value = item.split("=", 1)
        name = name.strip()
        if name:
            cookies[name] = value.strip()
    return cookies


def format_browser_prompt(messages: Sequence[Message], *, continuation: bool = False) -> str:
    """Kanonik Fusion mesajlarını tarayıcıya gönderilecek metne dök.

    `continuation=True` ise sohbet AÇIKTIR ve yalnızca yeni mesajlar gönderilir;
    sağlayıcının kendi bağlamı geçmişi zaten taşır. `False` ise sohbet yeni kuruluyordur
    ve geçmişin tamamı bu metne girer.

    DEVAM KİPİNDE ASİSTAN MESAJLARI GÖNDERİLMEZ — ölçüldü:

    Sohbet açıkken modelin kendi turu o konuşmanın İÇİNDEDİR. Onu bir kez daha
    göndermek, modele kendi araç çağrılarını yeni bir istek gibi gösterir ve model
    aynen tekrar üretir. Gerçek koşuda tam olarak bu oldu: üç dosya okundu, sonuçlar
    döndü, ardından model aynı üç okumayı yeniden istedi ve tekrar kapısı turu kesti.
    Stateless bir API'de tüm geçmişi göndermek zorunludur; stateful bir sohbette aynı
    şey "bunları yap" demektir.

    Araç sonuçları HANGİ ÇAĞRIYA ait olduklarını söyler. Üç sonucun da aynı başlıkla
    (`ARAÇ SONUCU (read_file, başarılı)`) gelmesi, modelin hangi dosyanın döndüğünü
    ayırt etmesini imkânsız kılıyordu.

    DEVAM TALİMATI EN BAŞTADIR — A/B ile ölçüldü (Gemini web, aynı kurulum, tek fark
    devam turunun biçimi):

        A) talimat sonda + başlıkta ham JSON  → aynı okumaları TEKRARLADI
        B) talimat başta + JSON yok           → write_file'a geçti, düzeltmeyi üretti

    İki sebep birlikte çalışıyordu. Talimat 3500 karakterlik dosya içeriğinin ARDINA
    düşüyordu ve model onu kaybediyordu. Ayrıca başlık `read_file {"path": "x.py"}`
    biçimindeydi — bu bir araç ÇAĞRISINA benziyor ve model onu taklit ediyordu.
    Tanımlayıcı bilgi korunur ama çağrı biçiminde değil.
    """
    if continuation:
        return _format_continuation(messages)
    calls_by_id = {call.id: call for message in messages for call in message.tool_calls}
    rendered: list[str] = []
    for message in messages:
        if message.role == "system":
            label = "SİSTEM"
        elif message.role == "assistant":
            label = "ASİSTAN"
        elif message.role == "tool":
            label = f"ARAÇ SONUCU ({_tool_result_label(message, calls_by_id)})"
        else:
            label = "KULLANICI"
        content = message.content.strip()
        if message.tool_calls:
            call_lines = ["[Önceki araç çağrıları]"]
            for call in message.tool_calls:
                call_lines.append(f"name: {call.name}")
                call_lines.append(f"arguments: {call.arguments}")
            content = "\n".join([content, *call_lines]).strip()
        rendered.append(f"### {ROLE_PREFIX}{label}\n{content}")
    # Talimat her iki kipte de tekrarlanır: web arayüzleri uzun sohbetlerde ilk
    # mesajdaki kuralları zayıflatır ve model biçimi bırakmaya başlar.
    rendered.append(
        f"### {ROLE_PREFIX}TALİMAT\nYukarıdaki araç sonuçları SENİN önceki çağrılarının cevabıdır; "
        "aynı çağrıları tekrar etme. Sonuçları kullanarak bir SONRAKİ adımı at: "
        f"ya yeni bir araç çağır ya da işi bitirip nihai cevabı ver.\n{_ANSWER_CONTRACT}"
    )
    rendered.append(_task_reminder(messages))
    return "\n\n".join(part for part in rendered if part)


def _task_reminder(messages: Sequence[Message]) -> str:
    """Kullanıcının görevini promptun EN SONUNA bir kez daha koy.

    Ölçüldü: sistem promptu + araç sözleşmesi + skill bloğu ~23.500 karakter,
    kullanıcının görevi ~150 karakter — çerçevenin %0,6'sı. Üstelik görevin
    ARDINDAN jenerik talimat bloğu geliyordu, yani modelin okuduğu SON şey görev
    değil kalıp metindi. Gerçek koşuda model, görev metninde dosya adı açıkça
    yazdığı hâlde "herhangi bir kullanıcı görevi belirtilmedi" diyerek turu
    bitirdi.

    Hatırlatma yeni bilgi taşımaz; yalnızca görevi en çok bakılan yere koyar.
    """
    gorev = next(
        (mesaj.content.strip() for mesaj in reversed(messages) if mesaj.role == "user"), ""
    )
    if not gorev:
        return ""
    return f"### {ROLE_PREFIX}GÖREV (yapılacak iş budur)\n{gorev}"


#: Her iki kipte de tekrarlanan nihai cevap sözleşmesi.
#:
#: `### FUSION//…` başlıkları ÇERÇEVEDİR, içerik değil; model onları taklit edip
#: kendini "sıradaki adımı sor" rolünde görüyordu. Kuralın ayıklama (bkz.
#: `strip_role_headers`) ile birlikte durmasının sebebi, ayıklamanın belirtiyi
#: temizlemesi ama nedenini ortadan kaldırmamasıdır.
#:
#: Nihai cevabın ŞEKLİ de burada söylenir: sistem promptundaki aynı kural, 3500
#: karakterlik araç çıktılarının ardında kalıp zayıflıyordu.
_ANSWER_CONTRACT = (
    "İlk yanıtında, ilk araç çağrının yanında 2-3 cümlelik bir AÇILIŞ yaz: isteği "
    "nasıl anladığın, hangi adımları izleyeceğin, ilk adımın ne olduğu. Sonraki "
    "çağrılarda tek satırlık kısa öncü yeter.\n"
    f"`{ROLE_PREFIX}` ile başlayan başlıkları KENDİ cevabında tekrarlama; onlar "
    "çerçevedir, senin rolün değildir.\n"
    "Kullanıcı görevini zaten verdi: ne yapacağını ona tekrar sorma. Gerçekten "
    "kullanıcının kararı olan bir seçim varsa ask_user aracını çağır; düzyazıyla "
    "soru sorup turu bitirme.\n"
    "İş bittiğinde nihai cevabında şunlar bulunur: ne yaptığın, hangi dosyaların "
    "değiştiği ve kullanıcının ne kontrol etmesi gerektiği. Bunu birkaç cümlede "
    "topla; adım adım günlük dökme.\n"
    "YALNIZCA bu turda gerçekten çağırdığın araçlarla değiştirdiğin dosyaları say. "
    "Okuduğun bir dosyada ZATEN var olan bir şeyi kendi işin gibi raporlama. "
    "Hiçbir şey değiştirmediysen bunu açıkça söyle — yapılmamış işi yapılmış gösterme."
)


def _tool_result_label(message: Message, calls_by_id: Mapping[str, ToolCall]) -> str:
    """Araç sonucunu HANGİ çağrıya ait olduğunu söyleyecek biçimde etiketle."""
    tool_name = message.name or "araç"
    status = "başarılı" if message.ok is not False else "hatalı"
    hedef = _call_subject(calls_by_id.get(message.tool_call_id or ""))
    if not hedef:
        return f"{tool_name} · {status}"
    return f"{tool_name} · {hedef} · {status}"


#: Bir çağrıyı tanımlayan alanlar, önem sırasıyla. Ham JSON yerine YALNIZCA bu
#: değer gösterilir: `read_file {"path": "x.py"}` biçimi bir araç çağrısına
#: benziyordu ve model onu taklit ediyordu (A/B ile ölçüldü).
_SUBJECT_FIELDS = ("path", "command", "pattern", "query", "url", "subcommand")


def _call_subject(call: ToolCall | None) -> str:
    """Çağrıyı tanımlayan tek değeri çıkar (dosya yolu, komut…)."""
    if call is None:
        return ""
    try:
        arguments = json.loads(call.arguments)
    except (json.JSONDecodeError, TypeError, ValueError):
        return ""
    if not isinstance(arguments, dict):
        return ""
    for field in _SUBJECT_FIELDS:
        value = arguments.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()[:80]
    return ""


#: Devam turunun BAŞINA konan yönerge. Sonda değil başta: 3500 karakterlik dosya
#: içeriğinin ardına düşen talimatı model kaybediyordu (A/B ile ölçüldü).
CONTINUATION_LEAD = (
    f"### {ROLE_PREFIX}SIRADAKİ ADIM\n"
    "Aşağıdaki araç sonuçları SENİN önceki çağrılarının cevabıdır — bu çağrıları "
    "ZATEN yaptın, tekrarlama. Sonuçları kullanarak bir sonraki adımı at: gereken "
    f"değişikliği yapan aracı çağır ya da iş bittiyse nihai cevabı ver.\n{_ANSWER_CONTRACT}"
)


def _format_continuation(messages: Sequence[Message]) -> str:
    """Açık sohbete gönderilecek metin: talimat başta, asistan turu yok."""
    calls_by_id = {call.id: call for message in messages for call in message.tool_calls}
    parcalar = [CONTINUATION_LEAD]
    for message in messages:
        if message.role == "assistant":
            continue
        if message.role == "tool":
            baslik = f"ARAÇ SONUCU · {_tool_result_label(message, calls_by_id)}"
        elif message.role == "system":
            baslik = "SİSTEM"
        else:
            baslik = "KULLANICI"
        parcalar.append(f"### {ROLE_PREFIX}{baslik}\n{message.content.strip()}")
    hatirlatma = _task_reminder(messages)
    if hatirlatma:
        parcalar.append(hatirlatma)
    return "\n\n".join(parcalar)


async def _launch_profile_context(
    chromium: Any,
    *,
    profile: Path,
    headless: bool,
    accept_downloads: bool,
) -> Any:
    """Kalıcı Fusion profiliyle bir tarayıcı bağlamı aç.

    Önce kullanıcının kurulu Chrome'u denenir (`channel="chrome"`), bulunamazsa
    Playwright'ın kendi Chromium'una düşülür — ikisi de yoksa hata yukarı taşınır.

    Argümanlar `**sözlük` ile değil AÇIKÇA verilir. Sözlükle açmak Playwright'ın
    tiplenmiş imzasını devre dışı bırakıyor ve yanlış yazılmış bir seçenek ancak
    çalışma anında ortaya çıkıyordu; iki çağrı yerinde de aynı liste elle
    kopyalanmıştı (RULES.md "Genel Tasarım": ortak davranış inline tekrar edilmez).
    """
    for channel in ("chrome", None):
        try:
            return await chromium.launch_persistent_context(
                str(profile),
                channel=channel,
                headless=headless,
                viewport={"width": 1440, "height": 1000},
                locale="tr-TR",
                accept_downloads=accept_downloads,
            )
        except Exception:
            # Kurulu Chrome yoksa paket içi Chromium denenir; o da açılamazsa
            # başarısızlık çağırana bildirilir.
            if channel is None:
                raise
    raise WebBrowserError("tarayıcı bağlamı açılamadı")


#: Bir hesapta aynı anda açık tutulacak en fazla sohbet. Ana tur + yardımcı
#: çağrılar (ders çıkarımı, öz-denetim, sıkıştırma) için yeterlidir.
MAX_OPEN_CONVERSATIONS = 4


@dataclass(slots=True)
class ConversationState:
    """Bir sağlayıcı/hesap için AÇIK KALAN web sohbeti.

    Neden var — ölçülmüş bir israf ve döngü kaynağı:

    Her araç turunda `new_chat_url`'e gidilip YENİ bir sohbet açılıyor ve konuşmanın
    TAMAMI tek düz metin bloğu olarak yeniden gönderiliyordu. Bunun üç sonucu vardı:

    1. Model gerçek bir araç-sonucu protokolü değil, "[Önceki araç çağrıları]" başlıklı
       bir metin görüyordu; aynı çağrıyı yeniden üretmesi bunun doğal sonucuydu.
    2. Her tur, geçmiş büyüdükçe daha uzun bir prompt demekti — gecikme ve kota israfı.
    3. Sağlayıcı arayüzünün kendi bağlam yönetimi hiç kullanılmıyordu.

    Artık sohbet açık kalır ve yalnızca YENİ mesajlar gönderilir. `sent_count` kaç
    kanonik mesajın gönderildiğini, `prefix_digest` o mesajların özetini tutar: geçmiş
    beklenen gibi UZAMADIYSA (sıkıştırma, yeni oturum, farklı araç seti) sohbet
    güvenli biçimde sıfırlanır ve her şey yeniden gönderilir.
    """

    page: Any
    sent_count: int = 0
    prefix_digest: str = ""
    #: Bu sohbette EN SON alınan yanıt. Bir sonraki turda tazelik ölçütüdür.
    last_answer: str = ""


def conversation_digest(messages: Sequence[Message]) -> str:
    """Mesaj önekinin kimliği — sohbetin GERÇEKTEN devam edip etmediğini söyler.

    Rol ve içerik birlikte özetlenir: yalnızca sayıya bakmak, geçmişi baştan yazılmış
    (sıkıştırılmış) bir konuşmayı devam sanmaya yol açardı ve model bambaşka bir
    bağlamda cevap verirdi.
    """
    digest = hashlib.sha256()
    for message in messages:
        digest.update(message.role.encode("utf-8", errors="replace"))
        digest.update(b"\x00")
        digest.update(message.content.encode("utf-8", errors="replace"))
        digest.update(b"\x01")
    return digest.hexdigest()


class BrowserSessionPool:
    """Süreç-yerel kalıcı Playwright bağlamları; sağlayıcı/hesap başına bir tane."""

    def __init__(self) -> None:
        self._playwright: Any | None = None
        self._contexts: dict[tuple[str, str, bool], Any] = {}
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}
        #: Sınır aşımında bırakılan, kapatılmayı bekleyen sayfalar.
        self._closing: list[Any] = []
        #: (sağlayıcı, hesap, konuşma kökü) → açık sohbet.
        #:
        #: Kök anahtarı ZORUNLU: ders çıkarımı ve öz-denetim gibi yardımcı çağrılar
        #: BAŞKA bir mesaj listesiyle gelir ve tek anahtarlı bir sözlükte ana sohbeti
        #: düşürüyorlardı. İzde görüldü: agent turunun ortasında ders çağrısı sohbeti
        #: sıfırlıyor, sonraki tur geçmişin tamamını yeniden göndermek zorunda kalıyordu.
        self._conversations: dict[tuple[str, str, str], ConversationState] = {}
        self._guard = asyncio.Lock()

    def lock_for(self, provider: str, account: str) -> asyncio.Lock:
        return self._locks.setdefault((provider, account), asyncio.Lock())

    def conversation(self, provider: str, account: str, root: str) -> ConversationState | None:
        return self._conversations.get((provider, account, root))

    def remember_conversation(
        self, provider: str, account: str, root: str, state: ConversationState
    ) -> None:
        self._conversations[(provider, account, root)] = state
        self._trim_conversations(provider, account)

    def _trim_conversations(self, provider: str, account: str) -> None:
        """Aynı hesapta çok fazla açık sayfa biriktirme.

        Her farklı konuşma kökü bir sekme demektir; sınırsız büyümesi tarayıcıyı
        boğar. En eski kökler bırakılır (sözlük ekleme sırasını korur).
        """
        ait = [key for key in self._conversations if key[0] == provider and key[1] == account]
        for key in ait[: max(0, len(ait) - MAX_OPEN_CONVERSATIONS)]:
            state = self._conversations.pop(key, None)
            if state is not None:
                self._closing.append(state.page)

    async def drop_conversation(self, provider: str, account: str, root: str) -> None:
        """Tek bir sohbeti bırak ve sayfasını kapat."""
        state = self._conversations.pop((provider, account, root), None)
        if state is None:
            return
        with contextlib.suppress(Exception):
            await state.page.close()

    async def drop_account_conversations(self, provider: str, account: str) -> None:
        """Bir hesabın TÜM sohbetlerini bırak (profil kapatılırken)."""
        for key in [k for k in self._conversations if k[0] == provider and k[1] == account]:
            await self.drop_conversation(provider, account, key[2])

    async def flush_closed(self) -> None:
        """Sınırı aşınca bırakılan sayfaları kapat."""
        while self._closing:
            page = self._closing.pop()
            with contextlib.suppress(Exception):
                await page.close()

    async def context_for(self, session: WebSessionConfig, credential: WebSessionCredential) -> Any:
        key = (session.provider, session.account, session.headless)
        async with self._guard:
            existing = self._contexts.get(key)
            if existing is not None:
                # A cookie may have been refreshed from the control panel while Fusion
                # keeps the browser context alive.  Re-inject it before every turn.
                await _inject_cookie_header(existing, session.provider, credential.token)
                return existing
            try:
                from playwright.async_api import async_playwright
            except ImportError as error:
                raise WebBrowserError(
                    "Playwright kurulu değil. Proje venv'inde `pip install -e '.[web]'` "
                    "ve `python -m playwright install chromium` çalıştır."
                ) from error
            if self._playwright is None:
                self._playwright = await async_playwright().start()
            profile = browser_profile_dir(session.provider, session.account)
            profile.mkdir(parents=True, exist_ok=True)
            clear_profile_singletons(profile)
            context = await _launch_profile_context(
                self._playwright.chromium,
                profile=profile,
                headless=session.headless,
                accept_downloads=False,
            )
            await _inject_cookie_header(context, session.provider, credential.token)
            self._contexts[key] = context
            return context

    async def close_session(self, provider: str, account: str) -> None:
        """Bir profile ait tüm (görünür/görünmez) bağlamları kapat.

        Chrome kalıcı profilleri KİLİTLER. Kontrol paneli, etkileşimli giriş penceresi
        açmadan ya da headless ayarını değiştirmeden önce bunu çağırır.
        """
        await self.drop_account_conversations(provider, account)
        async with self._guard:
            keys = [key for key in self._contexts if key[0] == provider and key[1] == account]
            contexts = [self._contexts.pop(key) for key in keys]
        for context in contexts:
            with contextlib.suppress(Exception):
                await context.close()

    async def close(self) -> None:
        for context in tuple(self._contexts.values()):
            with contextlib.suppress(Exception):
                await context.close()
        self._contexts.clear()
        if self._playwright is not None:
            with contextlib.suppress(Exception):
                await self._playwright.stop()
            self._playwright = None


_POOL = BrowserSessionPool()


async def close_all_browser_sessions() -> None:
    """Süreç biterken açık tüm tarayıcı bağlamlarını kapat.

    `BrowserSessionPool.close()` vardı ama HİÇBİR YERDEN çağrılmıyordu: `fusion agent`
    çıkınca headless Chrome sahipsiz kalıyordu. Ölçüldü — üç koşu sonrası profili
    tutan sekiz süreç birikmişti ve bu, `fusion serve`'ün kapanmasını da engelledi.
    """
    await _POOL.close()


async def close_browser_session(provider: str, account: str) -> None:
    """Release the persistent profile so a visible login window can use it."""
    await _POOL.close_session(provider, account)


#: İz dosyasında tutulan en fazla tur. Teşhis için son turlar yeter; dosya
#: sınırsız büyürse kullanıcının diskini sessizce doldurur.
MAX_TRACE_TURNS = 40


def _append_trace(
    trace_dir: Path, session: WebSessionConfig, *, prompt: str, answer: str, resumed: bool
) -> None:
    """Bir turu redakte ederek iz dosyasına ekle. Hata turu DÜŞÜRMEZ.

    Teşhis kaydı bir kolaylıktır: yazılamıyorsa (disk dolu, izin yok) kullanıcının
    turu bundan etkilenmemelidir.
    """
    try:
        trace_dir.mkdir(parents=True, exist_ok=True)
        path = trace_dir / f"{_slug(session.provider)}-{_slug(session.account)}.jsonl"
        satirlar = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        satirlar.append(
            json.dumps(
                {
                    "zaman": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "devam": resumed,
                    "gonderilen": redact(prompt),
                    "gelen": redact(answer),
                },
                ensure_ascii=False,
            )
        )
        path.write_text("\n".join(satirlar[-MAX_TRACE_TURNS:]) + "\n", encoding="utf-8")
        with contextlib.suppress(OSError):
            path.chmod(0o600)
    except OSError:
        return


def browser_turn_budget(session: WebSessionConfig, *, override_s: float | None = None) -> float:
    """Bir tarayıcı turuna verilecek saniye bütçesi.

    Kaynak yapılandırmadır; `override_s` yalnızca çağıranın (test) bütçeyi bilinçli
    olarak değiştirmesi içindir. Taban `MIN_BROWSER_TURN_S`: yapılandırmaya sıfır ya
    da saçma bir küçük değer girilse bile tur başlayacak kadar süre bulur.
    """
    return max(MIN_BROWSER_TURN_S, override_s if override_s is not None else session.timeout_s)


def build_browser_transport(
    session: WebSessionConfig,
    *,
    pool: BrowserSessionPool | None = None,
    timeout_s: float | None = None,
    trace_dir: Path | None = None,
) -> WebTransport:
    """Yapılandırılmış bir sağlayıcı/hesap için tarayıcı transport'u kur.

    Seçici/hazırlık arızası AYNI sağlayıcı ve AYNI izole profil içinde tam olarak bir
    kez yeniden denenir. Kimlik doğrulama, kota ve insan-doğrulama hataları yeniden
    denemenin ya da başka bir sağlayıcının ARKASINA GİZLENMEZ: kullanıcı gerçek sebebi
    görmelidir.

    Tur bütçesi YAPILANDIRMADAN gelir (`session.timeout_s`); `timeout_s` yalnızca
    testin bütçeyi kısaltması içindir. Eskiden bütçe `WEB_TIMEOUT_S` (20 sn) ile
    `min()`'lenerek hesaplanıyordu ve o sabit bir HTTP isteği bütçesidir: yapılandırma
    süreyi yalnızca KISALTABİLİYOR, hiçbir zaman uzatamıyordu. Sonuç ölçüldü — sayfa
    yükleme + yazma + tam streaming üretimin tamamı 20 saniyeye sıkışıyor ve her
    kodlama turu "yanıt 20 saniyede tamamlanmadı" ile düşüyordu.
    """
    definition = provider_definition(session.provider)
    manager = pool or _POOL

    async def _transport(
        credential: WebSessionCredential, messages: tuple[Message, ...], model: str
    ) -> str:
        del model  # Tarayıcı arayüzü hesabın kendi seçili modelini kullanır.
        lock = manager.lock_for(session.provider, session.account)
        async with lock:
            context = await manager.context_for(session, credential)
            limit = browser_turn_budget(session, override_s=timeout_s)
            deadline = time.monotonic() + limit
            last_selector_error: WebBrowserSelectorError | None = None

            for attempt in range(2):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    return await asyncio.wait_for(
                        _deliver_turn(manager, session, definition, context, messages, trace_dir),
                        timeout=max(1.0, remaining),
                    )
                except WebBrowserSelectorError as error:
                    last_selector_error = error
                    # Sohbet bilinmeyen bir duruma düştü: bırak, ikinci deneme
                    # sıfırdan başlasın. Aynı hesap, aynı profil — gizli yedek yok.
                    await manager.drop_conversation(
                        session.provider, session.account, conversation_digest(messages[:1])
                    )
                    if attempt == 0:
                        await asyncio.sleep(0.75)
                        continue
                    raise
                except TimeoutError as error:
                    await manager.drop_conversation(
                        session.provider, session.account, conversation_digest(messages[:1])
                    )
                    raise WebBrowserError(
                        f"{definition.name} yanıtı {limit:.0f} saniyede tamamlanmadı"
                    ) from error

            if last_selector_error is not None:
                raise last_selector_error
            raise WebBrowserError(f"{definition.name} yanıtı {limit:.0f} saniyede tamamlanmadı")

    return _transport


async def _deliver_turn(
    manager: BrowserSessionPool,
    session: WebSessionConfig,
    definition: BrowserProviderDefinition,
    context: Any,
    messages: tuple[Message, ...],
    trace_dir: Path | None = None,
    limit_s: float = DEFAULT_RESPONSE_WAIT_S,
) -> str:
    """Turu AÇIK sohbete ilet; sohbet yoksa ya da kopmuşsa yeniden kur.

    Devam edilebilirlik iki koşula bağlıdır: mesaj listesi UZAMIŞ olmalı ve daha önce
    gönderilen önek DEĞİŞMEMİŞ olmalı. İkincisi olmadan, bağlam sıkıştırıldığında ya da
    yeni bir oturum başladığında model bambaşka bir konuşmanın ortasında cevap verirdi.
    """
    # Konuşma kökü: İLK mesajın özeti. Ana agent turu hep aynı sistem promptuyla
    # başlar; ders çıkarımı gibi yardımcı çağrılar başka bir kökle gelir ve kendi
    # sohbetlerini alır. Böylece yardımcı bir çağrı ana sohbeti DÜŞÜRMEZ.
    root = conversation_digest(messages[:1])
    state = manager.conversation(session.provider, session.account, root)
    resumable = (
        state is not None
        and 0 < state.sent_count < len(messages)
        and conversation_digest(messages[: state.sent_count]) == state.prefix_digest
    )

    if resumable and state is not None:
        prompt = format_browser_prompt(messages[state.sent_count :], continuation=True)
        answer = await _send_turn(
            state.page, definition, prompt, previous=state.last_answer, limit_s=limit_s
        )
    else:
        await manager.drop_conversation(session.provider, session.account, root)
        page = await context.new_page()
        state = ConversationState(page=page)
        await _open_conversation(page, definition)
        prompt = format_browser_prompt(messages)
        answer = await _send_turn(page, definition, prompt, limit_s=limit_s)

    # Çerçeve, cevaba sızmadan burada kesilir: aşağıdaki katmanların hiçbiri
    # taşıma biçimini tanımak zorunda değildir.
    answer = strip_role_headers(answer)

    state.sent_count = len(messages)
    state.prefix_digest = conversation_digest(messages)
    state.last_answer = answer
    manager.remember_conversation(session.provider, session.account, root, state)
    await manager.flush_closed()
    if trace_dir is not None:
        _append_trace(trace_dir, session, prompt=prompt, answer=answer, resumed=resumable)
    return answer


async def open_login_browser(provider: str, account: str) -> None:
    """Görünür izole profili aç ve kullanıcı tarayıcıyı kapatana kadar bekle."""
    definition = provider_definition(provider)
    try:
        from playwright.async_api import async_playwright
    except ImportError as error:
        raise WebBrowserError(
            "Playwright kurulu değil. `pip install -e '.[web]'` ve "
            "`python -m playwright install chromium` çalıştır."
        ) from error
    profile = browser_profile_dir(provider, account)
    profile.mkdir(parents=True, exist_ok=True)
    clear_profile_singletons(profile)
    async with async_playwright() as playwright:
        context = await _launch_profile_context(
            playwright.chromium,
            profile=profile,
            headless=False,
            # Giriş sırasında indirme engellenmez: bazı sağlayıcılar doğrulama
            # akışında dosya indirtebiliyor.
            accept_downloads=True,
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(definition.home_url, wait_until="domcontentloaded", timeout=60_000)
        # Pencere, kullanıcı kapatana kadar açık kalır. Yoklama bilinçlidir: giriş
        # bitişini sağlayıcıya özgü bir seçiciye bağlamak, arayüz her değiştiğinde
        # kırılırdı.
        #
        # Bastırma gerekçesi (ASYNC110): kural, süreç İÇİ bir üreticinin
        # `asyncio.Event` ile işaret vermesini önerir. Burada koşulun sahibi dış bir
        # süreçtir (kullanıcının tarayıcı penceresi); Event'i set edecek üretici yoktur.
        while context.pages:  # noqa: ASYNC110
            await asyncio.sleep(0.5)
        with contextlib.suppress(Exception):
            await context.close()


async def _open_conversation(page: Any, definition: BrowserProviderDefinition) -> None:
    """Yeni bir sohbet aç. Yalnızca sohbet KURULURKEN çağrılır."""
    await page.goto(definition.new_chat_url, wait_until="domcontentloaded", timeout=60_000)


async def _run_page(page: Any, definition: BrowserProviderDefinition, prompt: str) -> str:
    """Yeni sohbet açıp tek tur çalıştır (sohbet sürekliliği kullanılmayan yol)."""
    await _open_conversation(page, definition)
    return strip_role_headers(await _send_turn(page, definition, prompt))


async def _send_turn(
    page: Any,
    definition: BrowserProviderDefinition,
    prompt: str,
    *,
    previous: str = "",
    limit_s: float = DEFAULT_RESPONSE_WAIT_S,
) -> str:
    """Açık bir sohbete tek mesaj gönder ve yanıtı bekle.

    `previous` bu sohbetten alınan SON yanıttır ve tazelik ölçütüdür.
    """
    # Web uygulaması kabuğu, mesaj alanından önce çizilebilir. Gövdenin herhangi bir
    # yerindeki “Sign in” yazısını oturum kaybı sayma; önce gerçek composer'ı bekle.
    input_locator = await _first_visible(page, definition.input_selectors, timeout_ms=15_000)
    if input_locator is None:
        await _raise_known_page_error(page, definition, ignore_clean=True)
        with contextlib.suppress(Exception):
            await page.reload(wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(0.75)
        input_locator = await _first_visible(page, definition.input_selectors, timeout_ms=20_000)

    if input_locator is None:
        await _raise_known_page_error(page, definition)
        raise WebBrowserSelectorError(
            f"not found: {definition.name} mesaj alanı bulunamadı; "
            "sayfa hazır olmayabilir veya web arayüzü değişmiş olabilir"
        )

    before = await _response_snapshot(page, definition.response_selectors)
    await _fill_editor(input_locator, prompt)
    send = await _first_visible(page, definition.send_selectors, timeout_ms=2_000)
    if send is not None:
        await send.click()
    else:
        await input_locator.press("Enter")

    return await _wait_for_response(
        page, definition, before, previous=previous, sent_prompt=prompt, limit_s=limit_s
    )


async def _fill_editor(locator: Any, text: str) -> None:
    try:
        await locator.fill(text)
        return
    except Exception:
        pass
    await locator.click()
    with contextlib.suppress(Exception):
        await locator.press("Control+A")
    with contextlib.suppress(Exception):
        await locator.press("Meta+A")
    await locator.press("Backspace")
    await locator.insert_text(text)


async def _first_visible(page: Any, selectors: Sequence[str], *, timeout_ms: int) -> Any | None:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        for selector in selectors:
            locator = page.locator(selector).last
            try:
                if await locator.count() and await locator.is_visible():
                    return locator
            except Exception:
                continue
        await asyncio.sleep(0.25)
    return None


async def _response_snapshot(page: Any, selectors: Sequence[str]) -> tuple[str, ...]:
    """Sayfadaki yanıtları oku. Seçiciler BİRLİK değil TERCİH SIRASIDIR.

    Ölçüldü (Gemini web): cevaba "COGNOiSe.com - The IBM Cognos Community" gibi
    alakasız bir metin karıştı. Kaynak modelin uydurması değil sayfanın kendisiydi
    — `model-response` geniş bir kaptır ve kaynak/atıf kartlarını da içerir.
    Seçiciler birleştirildiği için dar seçicinin temiz metni ile geniş seçicinin
    çöplü metni aynı listeye giriyor, okunan son öğe çöplü olan oluyordu.

    İlk sonuç veren seçici kazanır ve diğerlerine hiç bakılmaz — bu dosyanın
    geri kalanındaki davranışın aynısı (`_first_visible` de ilkini döndürür).
    Sıralama tanımda dardan genişe yazılır; geniş olanlar yalnızca arayüz
    değiştiğinde devreye giren yedeklerdir.

    Yan fayda: yanıt SAYISI da tutarlı olur. Birleştirmede aynı yanıt her eşleşen
    seçiciden bir kez sayılıyordu ve "yeni yanıt geldi mi" ölçütü seçici sayısına
    göre kayıyordu.
    """
    for selector in selectors:
        try:
            values = await page.locator(selector).all_inner_texts()
        except Exception:
            continue
        texts = tuple(_clean_text(value) for value in values if _clean_text(value))
        if texts:
            return texts
    return ()


async def _wait_for_response(
    page: Any,
    definition: BrowserProviderDefinition,
    before: tuple[str, ...],
    *,
    previous: str = "",
    sent_prompt: str = "",
    limit_s: float = DEFAULT_RESPONSE_WAIT_S,
) -> str:
    """Bu turun YENİ cevabını bekle. Doğrulanamazsa ESKİ cevabı döndürme.

    Ölçüldü (Gemini web, iz kaydı): iki ardışık tur birebir aynı cevabı döndürdü.
    Model tekrarlamıyordu — bu fonksiyon aynı cevabı ikinci kez okuyordu. Agent onu
    yeni sanıp aynı araçları tekrar çalıştırdı ve tekrar kapısı turu kesti. Yani
    kullanıcının "döngüye giriyor" dediği davranışın kaynağı buydu.

    İki gevşeklik düzeltildi:

    1. "Yeni cevap geldi" ölçütü metin karşılaştırmasına DA bakıyordu
       (`candidate not in before OR sayı arttı`). Metin tabanlı dal, sayfa henüz yeni
       yanıt öğesini oluşturmadan tetiklenebiliyordu. Artık tek ölçüt YENİ BİR YANIT
       ÖĞESİNİN VARLIĞIDIR: eşleşen yanıt sayısı artmalıdır.

    2. Süre dolduğunda `latest` (yani ÖNCEKİ turun cevabı) döndürülüyordu. Bu, sessizce
       yanlış veri teslim etmektir. Artık hata fırlatılır: doğrulanamayan bir yanıt,
       yanlış bir yanıttan iyidir.
    """
    deadline = time.monotonic() + limit_s
    latest = ""
    stable_since = time.monotonic()
    checks = 0
    while time.monotonic() < deadline:
        checks += 1
        current = await _response_snapshot(page, definition.response_selectors)
        # Yeni yanıt ÖĞESİ oluştu mu? Sayının artması, metnin değişmesinden daha
        # güvenilir bir işarettir: aynı metin tekrar üretilebilir, ama öğe sayısı
        # yalnızca gerçekten yeni bir yanıt eklendiğinde artar.
        candidate = current[-1] if current else ""
        # Tazelik ÜÇ koşulun birleşimidir. Yalnızca öğe sayısına bakmak yetmedi:
        # gerçek koşuda her tur BİR CEVAP GERİDEN yanıtlandı — gönderilen mesaj,
        # bir önceki turun cevabıyla karşılandı, agent onu yeni sanıp aynı araçları
        # tekrar çalıştırdı. Sayı büyümüş görünse bile metin ÖNCEKİYLE AYNIYSA bu
        # yeni bir yanıt değildir.
        saw_new = len(current) > len(before) and bool(candidate) and candidate != previous
        if candidate != latest:
            latest = candidate
            stable_since = time.monotonic()
        generating = await _any_visible(page, definition.stop_selectors)
        if saw_new and latest and not generating and time.monotonic() - stable_since >= 1.5:
            return latest
        if checks % 15 == 0:
            # BEKLERKEN yalnızca gerçekten ENGELLEYEN durumlar turu keser: oturum
            # kapalıysa ya da insan doğrulaması isteniyorsa cevap zaten gelmeyecek.
            #
            # Kota/hız uyarıları burada KESMEZ — ölçüldü: Gemini model kademesi
            # değiştirdiğinde bir uyarı bandı gösteriyor ve konuşmaya devam ediyor.
            # Bandı görüp turu kesmek, çalışan bir oturumu durduruyordu; kullanıcı
            # bunu kota sanıp yeni hesap açmıştı. Uyarı ancak cevap HİÇ gelmezse
            # anlamlıdır ve aşağıda, süre dolduğunda sınıflandırılır.
            await _raise_if_blocked(page, definition, sent_prompt=sent_prompt)
        await asyncio.sleep(0.35)
    await _raise_known_page_error(page, definition, ignore_clean=True, sent_prompt=sent_prompt)
    raise WebBrowserSelectorError(
        f"not found: {definition.name} bu tur için yeni bir yanıt üretmedi; "
        "mesaj gönderilmemiş ya da arayüz değişmiş olabilir"
    )


def _login_required_message(definition: BrowserProviderDefinition) -> str:
    """Oturum kapalı. Kullanıcıya ÇALIŞTIRILABİLİR bir çıkış ver."""
    return (
        f"authentication: {definition.name} oturumu açık değil veya süresi dolmuş.\n"
        f"{_cozum_adimlari(definition)}"
    )


def _human_verification_message(definition: BrowserProviderDefinition, marker: str) -> str:
    """İnsan doğrulaması. Bunu Fusion AŞAMAZ; kullanıcı bizzat tamamlamalıdır."""
    return (
        f"authentication: {definition.name} insan doğrulaması (captcha) istiyor. "
        "Bunu otomatik aşmak mümkün değil — doğrulamayı görünür tarayıcıda KENDİN "
        f"tamamlaman gerekiyor.\n{_cozum_adimlari(definition)}\n[sayfa işareti: {marker}]"
    )


def _cozum_adimlari(definition: BrowserProviderDefinition) -> str:
    """Somut çözüm adımları.

    Eskiden mesaj yalnızca "görünür giriş tarayıcısında tamamla" diyordu ve bunun
    NASIL açılacağını hiçbir yerde söylemiyordu. RULES.md: hata mesajı ne olduğunu,
    nedenini ve kullanıcının NE YAPABİLECEĞİNİ söyler. Komut buraya yazılır.
    """
    return (
        "Çözüm — görünür tarayıcıda doğrulamayı tamamla (aynı izole profil kullanılır, "
        "bittiğinde arka plan modu yeniden çalışır):\n"
        f"  python -m fusion_cli.providers.web_login {definition.id} <hesap>\n"
        "Hesap adı `/model` çıktısındaki model kimliğinin ortasındadır "
        f"(ör. `{definition.id}/main/auto` → hesap `main`).\n"
        "Ya da: `fusion serve` → Sağlayıcılar → ilgili oturum → 'Tarayıcıyla giriş yap'.\n"
        "Tarayıcı açılınca doğrulamayı yap ve pencereyi KAPAT; oturum kaydedilir."
    )


async def _raise_if_blocked(
    page: Any, definition: BrowserProviderDefinition, *, sent_prompt: str = ""
) -> None:
    """Yalnızca cevabı İMKÂNSIZ kılan durumları fırlat: oturum ve insan doğrulaması.

    `sent_prompt` KENDİ gönderdiğimiz metindir ve gövdeden çıkarılır; yoksa
    promptumuzdaki bir kelime sağlayıcının uyarısı sanılır.
    """
    if await _strong_login_signal(page, definition):
        raise WebBrowserAuthError(_login_required_message(definition))
    body = await _page_chrome_text(page, definition, sent_prompt=sent_prompt)
    dogrulama = _matched_marker(body, _CHALLENGE_MARKERS)
    if dogrulama is not None:
        raise WebBrowserAuthError(_human_verification_message(definition, dogrulama))


async def _raise_known_page_error(
    page: Any,
    definition: BrowserProviderDefinition,
    *,
    ignore_clean: bool = False,
    sent_prompt: str = "",
) -> None:
    """Classify real login, human-verification and quota pages.

    Body-wide substring checks are deliberately NOT authentication evidence. Gemini,
    ChatGPT and other apps may render a hidden/footer “Sign in” string while an
    authenticated app shell is still loading. Authentication requires either a known
    login URL or a visible provider-specific login control.
    """
    if await _strong_login_signal(page, definition):
        raise WebBrowserAuthError(_login_required_message(definition))

    body = await _page_chrome_text(page, definition, sent_prompt=sent_prompt)
    if not body and not ignore_clean:
        body = ""

    dogrulama = _matched_marker(body, _CHALLENGE_MARKERS)
    if dogrulama is not None:
        raise WebBrowserAuthError(_human_verification_message(definition, dogrulama))
    # Kota işaretleri DAR tutulur. "try again later" burada DEĞİLDİR ve bu ölçülmüş
    # bir hatanın sonucudur: Gemini geçici her arızada "Something went wrong, try
    # again later" gösteriyor ve Fusion bunu kota sanıp kullanıcıya "kotan doldu,
    # sonra dene" diyordu. Kullanıcı bunun üzerine yeni bir hesap açtı — oysa sorun
    # kota değildi. Yanlış teşhis, teşhis yokluğundan zararlıdır.
    kota = _matched_marker(body, _QUOTA_MARKERS)
    if kota is not None:
        raise WebBrowserError(
            f"{definition.name} kullanım/kota sınırı bildirdi; daha sonra yeniden dene "
            f"veya Fusion fallback zincirini kullan. [sayfa: {kota}]"
        )
    gecici = _matched_marker(body, _TRANSIENT_MARKERS)
    if gecici is not None:
        raise WebBrowserError(
            f"{definition.name} geçici bir hata bildirdi (kota DEĞİL). Aynı istek "
            "genellikle yeniden denendiğinde geçer; sorun sürerse tarayıcı oturumunu "
            f"yenile. [sayfa: {gecici}]"
        )


#: İnsan doğrulaması işaretleri — cevabı İMKÂNSIZ kılar, beklerken de fırlatılır.
_CHALLENGE_MARKERS = (
    "verify you are human",
    "checking your browser",
    "unusual traffic",
    "captcha",
    "insan olduğunuzu doğrulayın",
    "robot olmadığınızı",
)

#: GERÇEKTEN kota/hız sınırını söyleyen işaretler. Dar tutulur.
_QUOTA_MARKERS = (
    "too many requests",
    "rate limit",
    "you've reached your limit",
    "you have reached your limit",
    "çok fazla istek",
    "kullanım sınırına",
)

#: Geçici arıza işaretleri. Kotadan AYRI raporlanır çünkü kullanıcıya verilecek
#: tavsiye zıttır: kotada beklemek/hesap değiştirmek gerekir, geçici arızada
#: yeniden denemek yeter.
_TRANSIENT_MARKERS = (
    "something went wrong",
    "try again later",
    "bir şeyler ters gitti",
    "bir hata oluştu",
)


#: Eşleşen işaretin çevresinden gösterilecek karakter sayısı. Kısa tutulur: amaç
#: teşhis, sayfa içeriğini hata mesajına dökmek değil.
_MARKER_CONTEXT_CHARS = 70


def _matched_marker(body: str, markers: tuple[str, ...]) -> str | None:
    """Eşleşen işareti ve ÇEVRESİNİ döndür.

    Yalnızca "kota" demek yetmiyor: hangi ifadenin eşleştiğini görmeden yanlış
    pozitifi gerçek kotadan ayırt edemiyoruz. Bu, aynı hatayı üçüncü kez tahminle
    kovalamayı önler.
    """
    for marker in markers:
        index = body.find(marker)
        if index < 0:
            continue
        bas = max(0, index - _MARKER_CONTEXT_CHARS)
        son = min(len(body), index + len(marker) + _MARKER_CONTEXT_CHARS)
        parca = " ".join(body[bas:son].split())
        return f"…{parca}…"
    return None


#: Gönderilen metinden gövdeden silinecek en kısa satır uzunluğu.
#
# Kısa satırlar ("ok", "- evet", "###") sağlayıcının kendi arayüzünde de doğal
# olarak bulunur; onları silmek GERÇEK bir uyarıyı gizleyebilirdi. Eşik, silmenin
# yalnızca bize ait olduğu kesin olan uzun satırlarda çalışmasını sağlar.
MIN_SENT_LINE_STRIP = 12


def strip_sent_text(body: str, sent: str) -> str:
    """Fusion'ın KENDİ gönderdiği metni gövdeden çıkar. Saftır ve doğrudan test edilir.

    Satır satır çalışır: contenteditable alan satır sonlarını ve boşlukları
    normalize edebildiği için promptun tamamı gövdede birebir bulunmayabilir.
    """
    if not sent.strip():
        return body
    for line in sent.lower().splitlines():
        parca = line.strip()
        if len(parca) >= MIN_SENT_LINE_STRIP:
            body = body.replace(parca, " ")
    return body


async def _page_chrome_text(
    page: Any, definition: BrowserProviderDefinition, *, sent_prompt: str = ""
) -> str:
    """Sayfa metnini, BİZİM YAZDIĞIMIZ her şey çıkarılmış hâlde döndür.

    İki şey çıkarılır ve ikisi de ölçülmüş hatalardan gelir:

    - **Modelin cevabı** — gövde taraması modelin ürettiği metni de kapsıyordu:
      model "rate limit" ya da "try again later" yazdığı anda Fusion bunu
      sağlayıcının kota uyarısı sanıyordu.
    - **Gönderdiğimiz prompt** — sistem promptu sohbete YAZILIYOR ve gövdenin
      parçası oluyor. Prompta "insan doğrulaması (CAPTCHA)" cümlesi eklendiğinde
      Fusion kendi yazdığı kelimeyi okuyup "captcha istiyor" diye turu düşürdü.
      Kullanıcı gerçekten giriş yapmış olmasına rağmen hatayı almaya devam etti.

    Ortak ilke: sınıflandırma yalnızca UYGULAMANIN KENDİ arayüz metnine bakar.
    Kendi yazdığımız hiçbir şey kanıt değildir.
    """
    try:
        ham = str(await page.locator("body").inner_text(timeout=3_000))
    except Exception:
        return ""
    # Gövde, çıkarılacak parçalarla AYNI normalleştirmeden geçer. Bu şart:
    # `_response_snapshot` metinleri `_clean_text` ile normalleştiriyor ve
    # normalleştirilmiş metin ham gövdede BİREBİR bulunmuyordu — `replace`
    # sessizce hiçbir şey yapmıyordu. Ölçüldü: sistem promptunda 3+ ardışık
    # satır sonu var, `_clean_text` onları daraltıyor ve eşleşme kayboluyordu.
    # Bu kusur "modelin cevabını çıkar" düzeltmesinde de gizliden vardı.
    body = _clean_text(ham)
    # SOHBETİN TAMAMI çıkarılır: kullanıcı turları, model turları ve GEÇMİŞ.
    # Geçmiş kritik: sohbet sürdüğü için önceki turlarda yazdığımız promptlar
    # ekranda kalır ve yalnızca bu turun promptunu çıkarmak yetmez.
    for parca in await _response_snapshot(
        page, (*definition.history_selectors, *definition.response_selectors)
    ):
        if parca:
            body = body.replace(parca, " ")
    return strip_sent_text(body.lower(), sent_prompt)


_LOGIN_URL_MARKERS: dict[str, tuple[str, ...]] = {
    "chatgpt_web": ("auth.openai.com", "/auth/login", "/auth0/"),
    "claude_web": ("/login", "/oauth/", "accounts.google.com"),
    "gemini_web": ("accounts.google.com", "/signin/", "/identifier"),
    "copilot_web": ("login.live.com", "login.microsoftonline.com", "/oauth20_"),
}

_LOGIN_SELECTORS: dict[str, tuple[str, ...]] = {
    "chatgpt_web": (
        'form[action*="login"] input',
        'button[data-testid*="login"]',
        'a[href*="/auth/login"]',
    ),
    "claude_web": (
        'input[type="email"]',
        'form[action*="login"]',
        'a[href*="/login"]',
    ),
    "gemini_web": (
        'input[type="email"]',
        'input[type="password"]',
        'form[action*="signin"]',
        "div[data-identifier]",
    ),
    "copilot_web": (
        'input[type="email"]',
        'input[name="loginfmt"]',
        'form[action*="login"]',
    ),
}


async def _strong_login_signal(page: Any, definition: BrowserProviderDefinition) -> bool:
    """Return True only for strong, visible authentication evidence."""
    current_url = str(getattr(page, "url", "") or "").lower()
    if any(marker in current_url for marker in _LOGIN_URL_MARKERS.get(definition.id, ())):
        return True
    return await _any_visible(page, _LOGIN_SELECTORS.get(definition.id, ()))


async def _any_visible(page: Any, selectors: Sequence[str]) -> bool:
    for selector in selectors:
        locator = page.locator(selector).last
        try:
            if await locator.count() and await locator.is_visible():
                return True
        except Exception:
            continue
    return False


async def _inject_cookie_header(context: Any, provider: str, raw: str) -> None:
    if not raw.strip():
        return
    definition = provider_definition(provider)
    parsed = parse_cookie_header(raw)
    cookies: list[dict[str, object]] = []
    for url in definition.cookie_urls:
        for name, value in parsed.items():
            cookies.append(
                {
                    "name": name,
                    "value": value,
                    "url": url,
                    "secure": url.startswith("https://"),
                }
            )
    if cookies:
        # Some imported cookies have stricter attributes than a generic Cookie header can
        # represent.  Add individually so one rejected cookie does not discard the rest.
        for cookie in cookies:
            with contextlib.suppress(Exception):
                await context.add_cookies([cookie])


def _clean_text(value: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-._")
    return cleaned or "main"
