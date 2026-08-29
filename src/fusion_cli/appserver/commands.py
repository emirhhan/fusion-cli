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
Köprü bütün etkileşimli dalları terminal işleyicisinden önce yakalar; appserver
`prompt_toolkit`, `input()` veya `getpass` çağırmaz.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Literal, TypedDict

from ..cli.repl import model_flows, profiles_flow, provider_flow
from ..cli.repl.commands import CommandRegistry
from ..cli.repl.state import ReplState
from ..config.credentials import FernetSecretStore
from ..providers.registry import BUILTIN_PROVIDERS, ProviderDefinition
from ..ui import messages
from ..ui.picker import Choice


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
    """Metin adımının görünürlük ve yer tutucu bilgisi."""

    gizli: bool
    yer_tutucu: str


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


def list_commands(registry: CommandRegistry) -> list[dict[str, str]]:
    """Kayıt defterindeki bütün komutları uygulama menüsü biçiminde döndür."""
    return [
        {
            "ad": command.name,
            "aciklama": command.summary,
            "grup": command.group,
            "kullanim": command.usage,
        }
        for command in registry.all()
    ]


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
    try:
        payload = command_choices(state, canonical, argument)
        if payload is not None:
            return {"ok": True, "metin": "", "secici": payload}
        special = _run_interactive_completion(state, canonical, argument, secret_store=secret_store)
        if special is not None:
            return special
        return {"ok": True, "metin": command.handler(state, argument)}
    except Exception:  # araç sınırı: süreç ve hassas hata ayrıntıları korunur
        return _error(messages.APP_COMMAND_FAILED)


def command_choices(state: ReplState, name: str, argument: str = "") -> ChoicePayload | None:
    """Komutun sıradaki seçici/metin adımını döndür; yoksa `None`."""
    canonical = "development" if name.casefold() == "dev" else name.casefold()
    stripped = argument.strip()
    simple = _simple_choices(state, canonical) if not stripped else None
    if simple is not None:
        return simple
    if canonical == "development":
        return _development_choices(state, stripped)
    if canonical == "profiles":
        return _profiles_choices(state, stripped)
    if canonical == "providers":
        return _providers_choices(stripped)
    return None


def _simple_choices(state: ReplState, name: str) -> ChoicePayload | None:
    builders: dict[str, tuple[str, str, Sequence[Choice], str]] = {
        "level": ("kademe", messages.LEVEL_TITLE, model_flows.level_choices(state.config), ""),
        "mode": ("profil", messages.MODE_TITLE, model_flows.mode_choices(state.config), ""),
        "effort": ("yogunluk", messages.EFFORT_TITLE, model_flows.effort_choices(), ""),
        "model": ("model_eylemi", messages.CMD_MODEL, _model_choices(state), ""),
        "provider": ("saglayici", _provider_title(state), _provider_choices(state), ""),
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
            )
    return None


def _run_interactive_completion(
    state: ReplState,
    name: str,
    argument: str,
    *,
    secret_store: FernetSecretStore | None,
) -> CommandResult | None:
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
    source = model_flows.source_by_key(state.config, source_key)
    if action.casefold() != "uygula" or not separator or not separator2 or source is None:
        return _error(messages.APP_COMMAND_INVALID_SELECTION)
    wanted = model_id.strip()
    if not wanted:
        return _error(messages.APP_COMMAND_INVALID_SELECTION)
    result = model_flows.apply_development_model(state.config, wanted, paid=source.paid)
    state.config = result.config
    return {"ok": True, "metin": result.message}


def _apply_profile(state: ReplState, argument: str) -> CommandResult:
    words = argument.split()
    if len(words) != 3 or words[0].casefold() != "edit":
        return _error(messages.APP_COMMAND_INVALID_SELECTION)
    tier_name, candidate = words[1].casefold(), words[2]
    valid = {choice.value for choice in _profile_candidate_choices(state, tier_name, False)}
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
    step: str, title: str, command: str, prefix: str, *, secret: bool = False
) -> ChoicePayload:
    kind: Literal["metin", "gizli_metin"] = "gizli_metin" if secret else "metin"
    placeholder = "API anahtarı" if secret else "<sağlayıcı>/<model>"
    metadata: FreeText = {"gizli": secret, "yer_tutucu": placeholder}
    return _payload(step, kind, title, (), command, prefix, free_text=metadata)


def _wire_choice(choice: Choice) -> WireChoice:
    return {
        "deger": choice.value,
        "etiket": choice.label,
        "aciklama": choice.description,
    }


def _model_choices(state: ReplState) -> tuple[Choice, ...]:
    role_choices = (
        Choice(f"agent {state.config.agent.model}", "agent", state.config.agent.model),
        Choice(f"judge {state.config.judge.model}", "hakem", state.config.judge.model),
    )
    candidates = tuple(
        Choice(
            f"cand {candidate.name} {candidate.model}",
            f"aday {candidate.name}",
            candidate.model,
        )
        for candidate in state.config.candidates
    )
    return (*role_choices, *candidates)


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
        for provider in provider_flow._addable(BUILTIN_PROVIDERS)
    )


def _addable_provider(provider_id: str) -> ProviderDefinition | None:
    wanted = provider_id.casefold()
    return next(
        (
            provider
            for provider in provider_flow._addable(BUILTIN_PROVIDERS)
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
