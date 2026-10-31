"""Slash komut defterini uygulamanın Türkçe tel sözleşmesine köprüler.

`command_choices` her adımda aynı biçimi döndürür::

    {
        "adim": str,
        "tur": "secim" | "metin" | "gizli_metin",
        "baslik": str,
        "secenekler": [{"deger": str, "etiket": str, "aciklama": str}],
        "devam": {"komut": str, "arguman_on_eki": str},
        "serbest_metin": {"gizli": bool, "yer_tutucu": str} | None,
    }

Uygulama seçilen değeri `arguman_on_eki` sonuna ekler. Sonraki bir seçici varsa
aynı argümanla yeniden `command_choices`, akış tamamlandıysa `run_command` çağrılır.
Köprü, seçici açan sekiz komut yüzeyini (level/mode/effort/model/provider/
development/profiles edit/providers add) terminal işleyicisinden önce yakalar;
bunlar için appserver `prompt_toolkit`, `input()` veya `getpass` hiç çağırmaz.

Köprülenmemiş etkileşimli komutlar (örn. dinamik `/resume<kaynak>` ailesi —
argümansız çağrıldığında düz `pick()` açar) `run_command`'a hiç ulaşmadan,
terminal işleyicisi çağrılmadan `APP_COMMAND_UNSUPPORTED_INTERACTIVE` ile
reddedilir; `list_commands` bunları `destekleniyor: False` ile işaretler.
"""

from __future__ import annotations

import io
import logging
import re
from collections.abc import Callable, Sequence
from typing import Any, Literal, NotRequired, TypedDict

from rich.console import Console

from ..cli.repl import model_flows, output_style_command, profiles_flow, provider_flow, rewind
from ..cli.repl.commands import CommandRegistry, model_command_result
from ..cli.repl.state import ReplState
from ..config.credentials import FernetSecretStore
from ..core.constants import MAX_OUTPUT_CHARS
from ..providers.registry import BUILTIN_PROVIDERS, ProviderDefinition
from ..ui import messages
from ..ui.picker import Choice

_LOG = logging.getLogger(__name__)


class WireChoice(TypedDict):
    """Uygulamadaki tek seçim satırı."""

    deger: str
    etiket: str
    aciklama: str


class Continuation(TypedDict):
    """Seçimden sonra kurulacak slash komut argümanı."""

    komut: str
    arguman_on_eki: str


class FreeText(TypedDict):
    """Metin adımının görünürlük ve yer tutucu bilgisi.

    `saglayici` yalnız API anahtarı adımında gelir: uygulama değeri komut dizgesine
    (`/providers add <id> <anahtar>`) KATMADAN `kontrol.anahtar_kaydet {saglayici, deger}` ile
    gönderir (S1-24). Alanı bilmeyen eski istemci komut yoluna düşer; o yol çalışmaya devam eder.
    """

    gizli: bool
    yer_tutucu: str
    saglayici: NotRequired[str]


class ChoicePayload(TypedDict):
    """Task 5'in doğrudan tele yazabileceği sabit seçici yükü."""

    adim: str
    tur: Literal["secim", "metin", "gizli_metin"]
    baslik: str
    secenekler: list[WireChoice]
    devam: Continuation
    serbest_metin: FreeText | None


CommandResult = dict[str, Any]
PickerCall = Callable[..., str | None]

#: Bu ÖN EKLE başlayan komutlar terminal dışında hiç köprülenmedi: dinamik
#: `/resume<kaynak>` ailesi argümansız çağrıldığında düz REPL `pick()` açar
#: (bkz. `cli/repl/commands.py::_resume`). Appserver'da terminal yok; bu yüzden
#: bunlar `run_command`'a hiç girmeden açıkça reddedilir. Fusion'ın kendi `/resume`
#: ve `/branch` komutları da burada kalır: masaüstünün sekme modeli bunları kendi
#: istekleriyle (`sohbet.listele`, `sohbet.dallan`) yapar; slash yolu sekmeyi şaşırtırdı.
_UNSUPPORTED_INTERACTIVE_PREFIXES = ("resume", "branch")
#: Yalnız terminale özgü komutlar: masaüstünde karşılığı yok (tema/görünüm/tuş bağı/durum
#: satırı prompt_toolkit'e aittir). Ölçüldü (31 Ekim): "destekleniyor" görünüp kalıcı config
#: ya da keybindings.json yazıyor, masaüstünde hiçbir etkisi olmuyordu.
_TERMINAL_ONLY = frozenset({"theme", "tui", "search", "vim", "keybindings", "statusline"})


def _is_unsupported_interactive(name: str) -> bool:
    """Bu komut köprülenmemiş bir etkileşimli dal mı? (terminal işleyicisine düşer)"""
    return any(name.startswith(prefix) for prefix in _UNSUPPORTED_INTERACTIVE_PREFIXES)


def _is_terminal_only(name: str) -> bool:
    return name in _TERMINAL_ONLY


def list_commands(registry: CommandRegistry) -> list[dict[str, Any]]:
    """Kayıt defterindeki bütün komutları uygulama menüsü biçiminde döndür.

    `destekleniyor` alanı, komutun protokol üzerinden GERÇEKTEN çalıştırılabileceğini
    bildirir. `False` olan bir komut listede görünür ama `run_command` onu her zaman
    açık bir hatayla reddeder — sessizce etkisiz kalmaz.
    """
    return [
        {
            "ad": command.name,
            "aciklama": command.summary,
            "grup": command.group,
            "kullanim": command.usage,
            "destekleniyor": not (
                _is_unsupported_interactive(command.name) or _is_terminal_only(command.name)
            ),
        }
        for command in registry.all()
    ]


#: Metne çevirirken kullanılacak sanal konsol genişliği. Terminal genişliğine
#: bağlanmaz: masaüstünde terminal yoktur ve çıktı her makinede aynı olmalıdır.
RENDER_WIDTH = 100


async def render_command_text(registry: CommandRegistry, state: ReplState, name: str) -> str:
    """Kendi çıktısını basan komutu METİN olarak üret.

    `RENDERED_COMMANDS` kümesindeki komutlar (tips, help, models, cost, …)
    sonuç döndürmez; çıktılarını doğrudan konsola basar ve işleyicileri boş dize
    döner. Masaüstü yalnız işleyicinin dönüşünü gönderdiği için bu komutlar
    "çalıştırıldı" deyip hiçbir şey göstermiyordu.

    İçerik KOPYALANMAZ: TUI'nin kullandığı `help_view.render` aynen çağrılır,
    yalnız hedefi kayıt yapan bir konsoldur. Böylece iki yüzey ayrışamaz — biri
    güncellenip öteki eskide kalamaz.
    """
    from ..cli.repl import help_view

    console = Console(
        file=io.StringIO(),
        force_terminal=False,
        no_color=True,
        record=True,
        width=RENDER_WIDTH,
    )
    await help_view.render(name, state, registry, console)
    return _bounded(console.export_text().strip())


def _bounded(text: str) -> str:
    """Çıktıyı arayüzün taşıyabileceği boyuta indir; kesildiğini SÖYLE.

    Ölçüldü: `/lessons` 86 KB üretebiliyor. Sessizce kesmek kullanıcıya eksik
    listeyi tam sanmasına yol açardı; sınır aşılırsa satır sınırında kesilir ve
    nedeni yazılır.
    """
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    kesilmis = text[:MAX_OUTPUT_CHARS]
    son_satir = kesilmis.rfind("\n")
    if son_satir > 0:
        kesilmis = kesilmis[:son_satir]
    return f"{kesilmis}\n\n{messages.APP_COMMAND_TRUNCATED}"


def run_command(
    registry: CommandRegistry,
    state: ReplState,
    name: str,
    argument: str,
    *,
    secret_store: FernetSecretStore | None = None,
) -> CommandResult:
    """Komutu terminal girdisi açmadan çalıştır; ayrıntılı hata sızdırma."""
    command = registry.get(name)
    if command is None:
        return _error(messages.APP_COMMAND_UNKNOWN)
    canonical = command.name
    if _is_unsupported_interactive(canonical):
        return _error(messages.APP_COMMAND_UNSUPPORTED_INTERACTIVE)
    if _is_terminal_only(canonical):
        return _error(messages.APP_COMMAND_TERMINAL_ONLY)
    try:
        payload = command_choices(state, canonical, argument)
        if payload is not None:
            return {"ok": True, "metin": "", "secici": payload}
        special = _run_interactive_completion(state, canonical, argument, secret_store=secret_store)
        if special is not None:
            return special
        return {"ok": True, "metin": command.handler(state, argument)}
    except Exception as error:  # araç sınırı: süreç ve hassas hata ayrıntıları korunur
        # Kullanıcıya genel mesaj; neden günlükte (yalnız tür adı — ayrıntı sır taşıyabilir).
        # Ölçüldü (30 Ekim): hiç loglanmıyordu, ağ/config/katalog hatası iz bırakmıyordu.
        _LOG.error("Komut çalıştırılamadı (%s): %s", canonical, type(error).__name__)
        return _error(messages.APP_COMMAND_FAILED)


def command_choices(state: ReplState, name: str, argument: str = "") -> ChoicePayload | None:
    """Komutun sıradaki seçici/metin adımını döndür; yoksa `None`."""
    canonical = "development" if name.casefold() == "dev" else name.casefold()
    stripped = argument.strip()
    simple = _simple_choices(state, canonical) if not stripped else None
    if simple is not None:
        return simple
    if canonical == "model":
        return _model_step(state, stripped)
    if canonical == "development":
        return _development_choices(state, stripped)
    if canonical == "profiles":
        return _profiles_choices(state, stripped)
    if canonical == "providers":
        return _providers_choices(stripped)
    if canonical in ("rewind", "checkpoint"):
        return _rewind_choices(state, stripped)
    return None


def _rewind_choices(state: ReplState, argument: str) -> ChoicePayload | None:
    """`/rewind` iki adımdır: tur → kapsam. Tam argüman (`3 kod`) seçici açmaz.

    Masaüstü `komut.secenekler` ile aynı seçici deseni kullanır; sohbet geçmişi ve
    dosyalar `rewind_command` üzerinden, terminalle AYNI defterden geri sarılır.
    """
    entries = state.checkpoints.entries()
    if not entries:
        return None
    if not argument:
        return _payload(
            "tur", "secim", messages.REWIND_PICK_TURN, rewind.turn_choices(entries), "rewind", ""
        )
    if argument.isdigit() and state.checkpoints.find(int(argument)) is not None:
        return _payload(
            "kapsam",
            "secim",
            messages.REWIND_PICK_SCOPE,
            rewind.scope_choices(),
            "rewind",
            f"{argument} ",
        )
    return None


def _simple_choices(state: ReplState, name: str) -> ChoicePayload | None:
    builders: dict[str, tuple[str, str, Sequence[Choice], str]] = {
        "level": ("kademe", messages.LEVEL_TITLE, model_flows.level_choices(state.config), ""),
        "mode": ("profil", messages.MODE_TITLE, model_flows.mode_choices(state.config), ""),
        "effort": ("yogunluk", messages.EFFORT_TITLE, model_flows.effort_choices(), ""),
        "provider": ("saglayici", _provider_title(state), _provider_choices(state), ""),
        # Çıktı stili (P-068): masaüstü aynı listeyi seçici olarak gösterir.
        "output-style": (
            "cikti_stili",
            messages.OUTPUT_STYLE_TITLE,
            output_style_command.style_choices(state),
            "",
        ),
    }
    found = builders.get(name)
    if found is None:
        return None
    step, title, choices, prefix = found
    return _payload(step, "secim", title, choices, name, prefix)


def _development_choices(state: ReplState, argument: str) -> ChoicePayload | None:
    if not argument:
        return _payload(
            "kaynak",
            "secim",
            messages.DEV_SOURCE_TITLE,
            model_flows.source_choices(state.config),
            "development",
            "kaynak ",
        )
    words = argument.split()
    if len(words) != 2 or words[0].casefold() != "kaynak":
        return None
    source = model_flows.source_by_key(state.config, words[1])
    if source is None:
        return None
    prefix = f"uygula {source.key} "
    if source.fetcher is None:
        return _text_payload("model", messages.DEV_CUSTOM_PROMPT, "development", prefix)
    entries = source.fetcher()
    choices = model_flows.entries_to_choices(entries, state.config.profile_eligibility)
    title = (
        messages.DEV_MODEL_TITLE.format(source=source.label)
        if entries
        else messages.DEV_EMPTY_CATALOG
    )
    return _payload("model", "secim", title, choices, "development", prefix)


def _profiles_choices(state: ReplState, argument: str) -> ChoicePayload | None:
    words = argument.split()
    if words == ["edit"]:
        return _payload(
            "profil",
            "secim",
            messages.PROFILES_HEADER,
            model_flows.level_choices(state.config),
            "profiles",
            "edit ",
        )
    if len(words) not in (2, 3) or words[0].casefold() != "edit":
        return None
    if len(words) == 3 and words[2].casefold() != "incompatible":
        return None
    tier_name = words[1].casefold()
    show_incompatible = len(words) == 3
    choices = _profile_candidate_choices(state, tier_name, show_incompatible)
    return _payload(
        "aday",
        "secim",
        messages.PROFILES_EDIT_TITLE.format(name=tier_name),
        choices,
        "profiles",
        f"edit {tier_name} ",
    )


def _providers_choices(argument: str) -> ChoicePayload | None:
    words = argument.split()
    if words == ["add"]:
        return _payload(
            "saglayici",
            "secim",
            messages.CRED_TITLE,
            _credential_choices(),
            "providers",
            "add ",
        )
    if len(words) == 2 and words[0].casefold() == "add":
        provider = _addable_provider(words[1])
        if provider is not None:
            return _text_payload(
                "gizli_deger",
                messages.CRED_PROMPT.format(name=provider.name),
                "providers",
                f"add {provider.id} ",
                secret=True,
                provider_id=provider.id,
            )
    return None


def _run_interactive_completion(
    state: ReplState,
    name: str,
    argument: str,
    *,
    secret_store: FernetSecretStore | None,
) -> CommandResult | None:
    if name == "model":
        result = model_command_result(state, argument.split())
        state.config = result.config
        return {"ok": result.ok, "metin": result.message}
    if name == "provider":
        return _apply_provider(state, argument)
    if name == "development":
        return _apply_development(state, argument)
    if name == "profiles" and argument.strip().casefold().startswith("edit "):
        return _apply_profile(state, argument)
    if name == "providers" and argument.strip().casefold().startswith("add"):
        return _add_provider_secret(state, argument, secret_store)
    return None


def _apply_provider(state: ReplState, argument: str) -> CommandResult:
    valid = {choice.value for choice in _provider_choices(state)}
    selected = argument.strip().casefold()
    if selected not in valid:
        return _error(messages.APP_COMMAND_INVALID_SELECTION)
    result = provider_flow.choose_provider(state.config, picker=_fixed_picker(selected))
    state.config = result.config
    return {"ok": True, "metin": result.message}


def _apply_development(state: ReplState, argument: str) -> CommandResult:
    action, separator, rest = argument.strip().partition(" ")
    source_key, separator2, model_id = rest.partition(" ")
    if action.casefold() != "uygula" or not separator or not separator2:
        return _error(messages.APP_COMMAND_INVALID_SELECTION)
    return _apply_development_selection(state, source_key, model_id)


#: Model kimliğinde kabul edilmeyen kontrol karakterleri (satır sonu, NUL…). Komut dizgesine
#: gömülen kimlik satır sonuyla ikinci bir komuta bölünebiliyordu (U1-40).
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
#: Katalogdaki en uzun model kimliklerinin çok üstünde; yalnızca saçma girdiyi keser.
_MAX_MODEL_ID_CHARS = 512


def select_development_model(
    state: ReplState, source_key: object, model_id: object
) -> CommandResult:
    """`model.sec {kaynak, model}`: seçimi komut dizgesi KURMADAN uygula (U1-40).

    `/development uygula <kaynak> <model>` ile AYNI uygulayıcıyı (`apply_development_model`:
    NIM araç doğrulaması, kalıcı yazım) kullanır; ikinci bir model yönetimi yolu açılmaz.
    Girdi yapısaldır: kimlik tek bir alandır, boşlukta bölünmez; kontrol karakteri taşıyan
    ya da bilinmeyen kaynaklı istek reddedilir. Eski komut yolu çalışmaya devam eder.
    """
    if not isinstance(source_key, str) or not isinstance(model_id, str):
        return _error(messages.APP_COMMAND_INVALID_SELECTION)
    wanted = model_id.strip()
    if not wanted or len(wanted) > _MAX_MODEL_ID_CHARS or _CONTROL_CHARS.search(wanted):
        return _error(messages.APP_COMMAND_INVALID_SELECTION)
    try:
        return _apply_development_selection(state, source_key, wanted)
    except Exception as error:  # araç sınırı: `run_command` ile aynı hata sözleşmesi
        _LOG.error("Model seçimi uygulanamadı: %s", type(error).__name__)
        return _error(messages.APP_COMMAND_FAILED)


def _apply_development_selection(state: ReplState, source_key: str, model_id: str) -> CommandResult:
    source = model_flows.source_by_key(state.config, source_key)
    wanted = model_id.strip()
    if source is None or not wanted:
        return _error(messages.APP_COMMAND_INVALID_SELECTION)
    onceki = state.config
    result = model_flows.apply_development_model(onceki, wanted, paid=source.paid)
    state.config = result.config
    # `apply_development_model` başarısızlıkta (NIM araç doğrulaması geçmedi,
    # kimlik geçersiz…) AYNI config nesnesini değiştirmeden döndürür (bkz. o
    # fonksiyonun sözleşmesi); başarıda `replace()` ile YENİ bir nesne döner.
    # Ölçüldü (27 Eylül): bu satır öncesinde her zaman `ok: True` dönüyordu —
    # doğrulama reddettiğinde bile masaüstü seçim BAŞARILI sanılıyordu, çünkü
    # doğrulama o güne kadar yalnızca `session.py`'nin AYRI bir ön-kontrolünde
    # yapılıyordu ve bu fonksiyona hiç ulaşmıyordu. Doğrulama artık BURADA
    # (`apply_development_model` içinde) yapıldığına göre sonuç da doğru
    # yansımalı.
    return {"ok": result.config is not onceki, "metin": result.message}


def _apply_profile(state: ReplState, argument: str) -> CommandResult:
    words = argument.split()
    if len(words) != 3 or words[0].casefold() != "edit":
        return _error(messages.APP_COMMAND_INVALID_SELECTION)
    tier_name, candidate = words[1].casefold(), words[2]
    # `komut.secenekler edit <tier> incompatible` ile üretilen seçim yükü, devam
    # argümanı olarak SEÇİLENİN adını taşır — "incompatible" sözcüğü argümanda
    # kalmaz, bu yüzden burada hangi listeden geldiği bilinmez. `show_incompatible`
    # kapsamı yalnız EKLER (uygun + uyumsuz), hiç çıkarmaz; o yüzden doğrulama
    # her zaman geniş kapsamla yapılır — seçenek üretimiyle AYNI kaynak, uyumsuz
    # akıştan seçilen bir aday artık `APP_COMMAND_INVALID_SELECTION`a takılmaz.
    valid = {choice.value for choice in _profile_candidate_choices(state, tier_name, True)}
    if candidate not in valid:
        return _error(messages.APP_COMMAND_INVALID_SELECTION)
    result = profiles_flow.edit_profile_primary(
        state.config, tier_name, picker=_fixed_picker(candidate)
    )
    state.config = result.config
    return {"ok": True, "metin": result.message}


def _add_provider_secret(
    state: ReplState, argument: str, store: FernetSecretStore | None
) -> CommandResult:
    words = argument.split(maxsplit=2)
    if len(words) != 3 or words[0].casefold() != "add":
        return _error(messages.APP_COMMAND_INVALID_SELECTION)
    provider = _addable_provider(words[1])
    if provider is None or not words[2].strip():
        return _error(messages.APP_COMMAND_INVALID_SELECTION)
    active_store = store if store is not None else _default_secret_store()
    result = provider_flow.add_credential(
        active_store,
        picker=_fixed_picker(provider.id),
        ask_secret=lambda _prompt: words[2],
    )
    expected = messages.CRED_SAVED.format(name=provider.name, env=provider.auth_env)
    if result == expected or result in (messages.CRED_NO_KEY, messages.PICKER_CANCELLED):
        return {"ok": True, "metin": result}
    return _error(messages.APP_COMMAND_FAILED)


def _payload(
    step: str,
    kind: Literal["secim", "metin", "gizli_metin"],
    title: str,
    choices: Sequence[Choice],
    command: str,
    prefix: str,
    *,
    free_text: FreeText | None = None,
) -> ChoicePayload:
    return {
        "adim": step,
        "tur": kind,
        "baslik": title,
        "secenekler": [_wire_choice(choice) for choice in choices],
        "devam": {"komut": command, "arguman_on_eki": prefix},
        "serbest_metin": free_text,
    }


def _text_payload(
    step: str,
    title: str,
    command: str,
    prefix: str,
    *,
    secret: bool = False,
    provider_id: str | None = None,
) -> ChoicePayload:
    kind: Literal["metin", "gizli_metin"] = "gizli_metin" if secret else "metin"
    placeholder = "API anahtarı" if secret else "<sağlayıcı>/<model>"
    metadata: FreeText = {"gizli": secret, "yer_tutucu": placeholder}
    if provider_id is not None:
        metadata["saglayici"] = provider_id
    return _payload(step, kind, title, (), command, prefix, free_text=metadata)


def _wire_choice(choice: Choice) -> WireChoice:
    return {
        "deger": choice.value,
        "etiket": choice.label,
        "aciklama": choice.description,
    }


#: `/model` seçicisinde rolün ardından kaynak adımını açan anahtar sözcük.
_MODEL_SOURCE_STEP = "kaynak"


def _model_step(state: ReplState, argument: str) -> ChoicePayload | None:
    """`/model` seçicisinin sıradaki adımı: rol → kaynak → model.

    Eskiden tek adım vardı ve seçenek değerleri rolün MEVCUT model kimliğini
    taşıyordu (`agent gemini_web/main/auto`). Seçim aynı modeli yeniden
    uyguluyor, kullanıcı da yalnız zaten kullandığı modeli görüyordu; ikinci
    adım ise seçenek üretmediği için "Bilinmeyen komut." dönüyordu.
    """
    words = argument.split()
    if not words:
        return _payload("rol", "secim", messages.CMD_MODEL, _model_role_choices(state), "model", "")

    role = _model_role(words)
    if role is None:
        return None
    kalan = words[len(role.split()) :]

    if not kalan:
        return _payload(
            "kaynak",
            "secim",
            messages.DEV_SOURCE_TITLE,
            model_flows.source_choices(state.config),
            "model",
            f"{role} {_MODEL_SOURCE_STEP} ",
        )
    if len(kalan) != 2 or kalan[0].casefold() != _MODEL_SOURCE_STEP:
        return None

    source = model_flows.source_by_key(state.config, kalan[1])
    if source is None:
        return None
    prefix = f"{role} "
    if source.fetcher is None:
        return _text_payload("model", messages.DEV_CUSTOM_PROMPT, "model", prefix)
    entries = source.fetcher()
    choices = model_flows.entries_to_choices(entries, state.config.profile_eligibility)
    title = (
        messages.DEV_MODEL_TITLE.format(source=source.label)
        if entries
        else messages.DEV_EMPTY_CATALOG
    )
    return _payload("model", "secim", title, choices, "model", prefix)


def _model_role(words: list[str]) -> str | None:
    """Argümanın başındaki rolü çöz: `agent`, `judge` ya da `cand <ad>`."""
    head = words[0].casefold()
    if head in {"agent", "judge"}:
        return head
    if head == "cand" and len(words) >= 2:
        return f"cand {words[1]}"
    return None


def _model_role_choices(state: ReplState) -> tuple[Choice, ...]:
    """Roller. Değer model kimliği TAŞIMAZ; taşısa seçim hiçbir şeyi değiştirmezdi."""
    return (
        Choice("agent", "agent", state.config.agent.model),
        Choice("judge", "hakem", state.config.judge.model),
        *(
            Choice(f"cand {candidate.name}", f"aday {candidate.name}", candidate.model)
            for candidate in state.config.candidates
        ),
    )


def _provider_choices(state: ReplState) -> tuple[Choice, ...]:
    captured: tuple[Choice, ...] = ()

    def capture(choices: Sequence[Choice], **_kwargs: object) -> None:
        nonlocal captured
        captured = tuple(choices)
        return None

    provider_flow.choose_provider(state.config, picker=capture)
    return captured


def _provider_title(state: ReplState) -> str:
    current = messages.PROVIDER_CURRENT.format(name=state.config.runtime.provider)
    return f"{current}\n\n{messages.PROVIDER_TITLE}"


def _profile_candidate_choices(
    state: ReplState, tier_name: str, show_incompatible: bool
) -> tuple[Choice, ...]:
    captured: tuple[Choice, ...] = ()

    def capture(choices: Sequence[Choice], **_kwargs: object) -> None:
        nonlocal captured
        captured = tuple(choices)
        return None

    profiles_flow.edit_profile_primary(
        state.config,
        tier_name,
        picker=capture,
        show_incompatible=show_incompatible,
    )
    return captured


def _credential_choices() -> tuple[Choice, ...]:
    return tuple(
        Choice(provider.id, provider.name, provider.auth_env or "")
        for provider in provider_flow.addable_providers(BUILTIN_PROVIDERS)
    )


def _addable_provider(provider_id: str) -> ProviderDefinition | None:
    wanted = provider_id.casefold()
    return next(
        (
            provider
            for provider in provider_flow.addable_providers(BUILTIN_PROVIDERS)
            if provider.id == wanted
        ),
        None,
    )


def _fixed_picker(value: str) -> PickerCall:
    def choose(_choices: Sequence[Choice], **_kwargs: object) -> str:
        return value

    return choose


def _default_secret_store() -> FernetSecretStore:
    from ..config.keys import secret_key
    from ..config.paths import credentials_file

    return FernetSecretStore(credentials_file(), secret_key=secret_key())


def _error(message: str) -> CommandResult:
    return {"ok": False, "metin": message}
