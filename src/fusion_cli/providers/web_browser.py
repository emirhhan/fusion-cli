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
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config.models import WebSessionConfig
from ..config.paths import user_data_dir
from ..core.constants import WEB_TIMEOUT_S
from ..core.types import Message
from .web_session import WebSessionCredential, WebTransport


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
            'textarea',
        ),
        send_selectors=(
            'button[data-testid="send-button"]',
            'button[aria-label*="Send"]',
            'button[aria-label*="Gönder"]',
        ),
        response_selectors=(
            '[data-message-author-role="assistant"]',
            '[data-testid^="conversation-turn-"] [data-message-author-role="assistant"]',
            'article[data-testid^="conversation-turn-"]',
        ),
        stop_selectors=(
            'button[data-testid="stop-button"]',
            'button[aria-label*="Stop"]',
            'button[aria-label*="Durdur"]',
        ),
        login_markers=("log in", "sign up", "giriş yap", "oturum aç"),
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
            'textarea',
        ),
        send_selectors=(
            'button[aria-label*="Send"]',
            'button[aria-label*="Gönder"]',
            'button[data-testid*="send"]',
        ),
        response_selectors=(
            '[data-testid="assistant-message"]',
            '[data-is-streaming] .font-claude-message',
            '.font-claude-message',
            'div[data-testid^="message-"]',
        ),
        stop_selectors=(
            'button[aria-label*="Stop"]',
            'button[aria-label*="Durdur"]',
        ),
        login_markers=("log in", "continue with google", "giriş yap", "oturum aç"),
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
            'textarea[aria-label]',
            'textarea',
        ),
        send_selectors=(
            'button[aria-label*="Send"]',
            'button[aria-label*="Gönder"]',
            'button.send-button',
        ),
        response_selectors=(
            'model-response .model-response-text',
            'model-response',
            '.model-response-text',
            '[data-test-id="response"]',
        ),
        stop_selectors=(
            'button[aria-label*="Stop"]',
            'button[aria-label*="Durdur"]',
        ),
        login_markers=("sign in", "oturum aç", "giriş yap", "choose an account"),
        default_models=("auto",),
        cookie_hint=(
            "gemini.google.com isteğinin tam Cookie başlığı; "
            "Google için tarayıcıyla giriş önerilir"
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
            'textarea[placeholder]',
            'textarea[aria-label]',
            'div[contenteditable="true"]',
            'textarea',
        ),
        send_selectors=(
            'button[aria-label*="Submit"]',
            'button[aria-label*="Send"]',
            'button[aria-label*="Gönder"]',
        ),
        response_selectors=(
            '[data-content="ai-message"]',
            '[data-testid="copilot-response"]',
            '.ac-textBlock',
            'cib-message-group[source="bot"]',
        ),
        stop_selectors=(
            'button[aria-label*="Stop"]',
            'button[aria-label*="Durdur"]',
        ),
        login_markers=("sign in", "oturum aç", "giriş yap", "microsoft account"),
        default_models=("auto",),
        cookie_hint=(
            "copilot.microsoft.com oturumundaki tam Cookie başlığı; "
            "tarayıcıyla giriş önerilir"
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


def format_browser_prompt(messages: Sequence[Message]) -> str:
    """Kanonik Fusion mesajlarını tek ve kendi kendine yeten bir prompt'a dök.

    DİKKAT: her sağlayıcı çağrısı YENİ bir web sohbeti açtığı için geçmişin tamamı
    her turda yeniden gönderilir. Araç sonuçları açıkça etiketlenir ki model bir
    sonraki turda taklit araç biçimini üretebilsin.
    """
    rendered: list[str] = []
    for message in messages:
        if message.role == "system":
            label = "SİSTEM"
        elif message.role == "assistant":
            label = "ASİSTAN"
        elif message.role == "tool":
            tool_name = message.name or "araç"
            status = "başarılı" if message.ok is not False else "hatalı"
            label = f"ARAÇ SONUCU ({tool_name}, {status})"
        else:
            label = "KULLANICI"
        content = message.content.strip()
        if message.tool_calls:
            call_lines = ["[Önceki araç çağrıları]"]
            for call in message.tool_calls:
                call_lines.append(f"name: {call.name}")
                call_lines.append(f"arguments: {call.arguments}")
            content = "\n".join([content, *call_lines]).strip()
        rendered.append(f"### {label}\n{content}")
    rendered.append(
        "### TALİMAT\nYalnızca bu konuşmadaki en son kullanıcı/araç sonucuna cevap ver. "
        "Önceki ASİSTAN metnini tekrar etme."
    )
    return "\n\n".join(rendered)


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


class BrowserSessionPool:
    """Süreç-yerel kalıcı Playwright bağlamları; sağlayıcı/hesap başına bir tane."""

    def __init__(self) -> None:
        self._playwright: Any | None = None
        self._contexts: dict[tuple[str, str, bool], Any] = {}
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    def lock_for(self, provider: str, account: str) -> asyncio.Lock:
        return self._locks.setdefault((provider, account), asyncio.Lock())

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
        async with self._guard:
            keys = [
                key
                for key in self._contexts
                if key[0] == provider and key[1] == account
            ]
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


async def close_browser_session(provider: str, account: str) -> None:
    """Release the persistent profile so a visible login window can use it."""
    await _POOL.close_session(provider, account)


def build_browser_transport(
    session: WebSessionConfig,
    *,
    pool: BrowserSessionPool | None = None,
    timeout_s: float = WEB_TIMEOUT_S,
) -> WebTransport:
    """Yapılandırılmış bir sağlayıcı/hesap için tarayıcı transport'u kur.

    Seçici/hazırlık arızası AYNI sağlayıcı ve AYNI izole profil içinde tam olarak bir
    kez yeniden denenir. Kimlik doğrulama, kota ve insan-doğrulama hataları yeniden
    denemenin ya da başka bir sağlayıcının ARKASINA GİZLENMEZ: kullanıcı gerçek sebebi
    görmelidir.
    """
    definition = provider_definition(session.provider)
    manager = pool or _POOL

    async def _transport(
        credential: WebSessionCredential, messages: tuple[Message, ...], model: str
    ) -> str:
        del model  # Browser UI currently uses the provider account's selected/default model.
        lock = manager.lock_for(session.provider, session.account)
        async with lock:
            context = await manager.context_for(session, credential)
            limit = max(10.0, min(timeout_s, session.timeout_s))
            deadline = time.monotonic() + limit
            last_selector_error: WebBrowserSelectorError | None = None

            for attempt in range(2):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                page = await context.new_page()
                try:
                    return await asyncio.wait_for(
                        _run_page(page, definition, format_browser_prompt(messages)),
                        timeout=max(1.0, remaining),
                    )
                except WebBrowserSelectorError as error:
                    last_selector_error = error
                    if attempt == 0:
                        # Same account/provider, fresh page only. No hidden fallback.
                        await asyncio.sleep(0.75)
                        continue
                    raise
                except TimeoutError as error:
                    raise WebBrowserError(
                        f"{definition.name} yanıtı {limit:.0f} saniyede tamamlanmadı"
                    ) from error
                finally:
                    with contextlib.suppress(Exception):
                        await page.close()

            if last_selector_error is not None:
                raise last_selector_error
            raise WebBrowserError(
                f"{definition.name} yanıtı {limit:.0f} saniyede tamamlanmadı"
            )

    return _transport


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


async def _run_page(page: Any, definition: BrowserProviderDefinition, prompt: str) -> str:
    await page.goto(definition.new_chat_url, wait_until="domcontentloaded", timeout=60_000)

    # Web uygulaması kabuğu, mesaj alanından önce çizilebilir. Gövdenin herhangi bir
    # yerindeki “Sign in” yazısını oturum kaybı sayma; önce gerçek composer'ı bekle.
    input_locator = await _first_visible(page, definition.input_selectors, timeout_ms=15_000)
    if input_locator is None:
        await _raise_known_page_error(page, definition, ignore_clean=True)
        with contextlib.suppress(Exception):
            await page.reload(wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(0.75)
        input_locator = await _first_visible(
            page, definition.input_selectors, timeout_ms=20_000
        )

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

    return await _wait_for_response(page, definition, before)


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
    texts: list[str] = []
    for selector in selectors:
        try:
            values = await page.locator(selector).all_inner_texts()
        except Exception:
            continue
        texts.extend(_clean_text(value) for value in values if _clean_text(value))
    return tuple(texts)


async def _wait_for_response(
    page: Any,
    definition: BrowserProviderDefinition,
    before: tuple[str, ...],
) -> str:
    deadline = time.monotonic() + 180
    latest = ""
    stable_since = time.monotonic()
    saw_new = False
    checks = 0
    while time.monotonic() < deadline:
        checks += 1
        current = await _response_snapshot(page, definition.response_selectors)
        candidate = current[-1] if current else ""
        if candidate and (candidate not in before or len(current) > len(before)):
            saw_new = True
        if candidate != latest:
            latest = candidate
            stable_since = time.monotonic()
        generating = await _any_visible(page, definition.stop_selectors)
        if saw_new and latest and not generating and time.monotonic() - stable_since >= 1.5:
            return latest
        if checks % 15 == 0:
            await _raise_known_page_error(page, definition, ignore_clean=True)
        await asyncio.sleep(0.35)
    await _raise_known_page_error(page, definition, ignore_clean=True)
    if latest:
        return latest
    raise WebBrowserSelectorError(
        f"not found: {definition.name} cevap alanı bulunamadı; "
        "oturum veya web seçicileri değişmiş olabilir"
    )


async def _raise_known_page_error(
    page: Any,
    definition: BrowserProviderDefinition,
    *,
    ignore_clean: bool = False,
) -> None:
    """Classify real login, human-verification and quota pages.

    Body-wide substring checks are deliberately NOT authentication evidence. Gemini,
    ChatGPT and other apps may render a hidden/footer “Sign in” string while an
    authenticated app shell is still loading. Authentication requires either a known
    login URL or a visible provider-specific login control.
    """
    if await _strong_login_signal(page, definition):
        raise WebBrowserAuthError(
            f"authentication: {definition.name} oturumu açık değil veya süresi dolmuş. "
            "Fusion Control Panel'den 'Tarayıcıyla giriş yap'ı aç."
        )

    try:
        body = (await page.locator("body").inner_text(timeout=3_000)).lower()
    except Exception:
        if ignore_clean:
            return
        body = ""

    challenge_markers = (
        "verify you are human",
        "checking your browser",
        "unusual traffic",
        "captcha",
        "insan olduğunuzu doğrulayın",
        "robot olmadığınızı",
    )
    if any(marker in body for marker in challenge_markers):
        raise WebBrowserAuthError(
            f"authentication: {definition.name} insan doğrulaması istiyor. "
            "Arka plan modunu kapatıp "
            "Fusion'ın görünür giriş tarayıcısında doğrulamayı kendin tamamla."
        )
    rate_markers = (
        "too many requests",
        "rate limit",
        "you've reached your limit",
        "you have reached your limit",
        "try again later",
        "çok fazla istek",
        "kullanım sınırına",
    )
    if any(marker in body for marker in rate_markers):
        raise WebBrowserError(
            f"{definition.name} kullanım/kota sınırı bildirdi; daha sonra yeniden dene "
            "veya Fusion fallback zincirini kullan."
        )


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
        'div[data-identifier]',
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
