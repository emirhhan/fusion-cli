"""Web sağlayıcı arayüz seçicileri — koddan ayrı, pakete gömülü JSON (P1-43).

Ölçüldü (30 Ekim): ChatGPT/Gemini/Claude/Copilot ön yüz seçicileri `web_browser.py`
içine kodlanmıştı (`jslog^='300142'`, `bard-mode-option-*`, `data-markdown-text-style`…).
Sağlayıcının her ön yüz dağıtımı bunları kırabilir; yorumlar bunun 22 Eylül ve 18 Ekim'de
iki kez olduğunu belgeliyor ve kullanıcıya her seferinde "zaman aşımı" olarak yansıdı.
Seçici düzeltmesi artık `data/web-selectors.json` dosyasında yapılır.

KAPSAM SINIRI: dosya YALNIZ paketle gelir. Uzaktan indirme/güncelleme yoktur — yeni bir
dağıtım ve güven kanalı açmak ayrı bir üründür. Dosya bozuksa ya da şemaya uymuyorsa
`WebSelectorsError` fırlar (sessiz varsayılan yok): seçicisiz sağlayıcı sessizce
çalışmıyor görünmek yerine açık hata verir.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from importlib import resources

from ..core.errors import FusionError
from ..core.web_provenance import ASSISTANT_ROLE_EVIDENCE

_RESOURCE_PACKAGE = "fusion_cli.providers"
_RESOURCE_PATH = ("data", "web-selectors.json")
#: Alan adları `_` ile başlayan anahtarlar açıklama içindir ve yok sayılır.
_NOTE_PREFIX = "_"
_SUPPORTED_VERSION = 1

#: Bir sağlayıcıda BOŞ olamayan alanlar: bunlar olmadan tur hiç başlayamaz.
_REQUIRED_LISTS = ("input", "send", "response", "stop", "history")
#: Boş olabilen alanlar: yalnız ölçülmüş sağlayıcı için doldurulur.
_OPTIONAL_LISTS = ("tier", "model_menu", "image", "origin_roles", "origin_ids")


class WebSelectorsError(FusionError):
    """Seçici dosyası okunamadı ya da şemaya uymuyor."""


@dataclass(frozen=True, slots=True)
class ProviderSelectors:
    """Bir sağlayıcının DOM seçicileri; her liste dardan genişedir."""

    input: tuple[str, ...]
    send: tuple[str, ...]
    response: tuple[str, ...]
    stop: tuple[str, ...]
    history: tuple[str, ...]
    tier: tuple[str, ...] = ()
    model_menu: tuple[str, ...] = ()
    image: tuple[str, ...] = ()
    origin_roles: tuple[str, ...] = ()
    origin_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WebSelectors:
    """Dosyanın tipli karşılığı."""

    providers: Mapping[str, ProviderSelectors]
    gemini_upload_menu_trigger: str
    gemini_upload_option: str
    model_option_gemini: str
    model_option_default: str
    challenge_dom: tuple[str, ...]
    schema_version: str = "1"
    bundle_digest: str = ""


def parse_web_selectors(raw: object) -> WebSelectors:
    """Ham JSON'u doğrula ve tipli nesneye çevir (bilinmeyen anahtar = hata)."""
    root = _mapping(raw, "kök")
    _reject_unknown(
        root, {"version", "providers", "gemini_upload", "model_option", "challenge_dom"}
    )
    if root.get("version") != _SUPPORTED_VERSION:
        raise WebSelectorsError(
            f"web-selectors.json sürümü desteklenmiyor: {root.get('version')!r} "
            f"(beklenen {_SUPPORTED_VERSION})."
        )
    providers_raw = _mapping(root.get("providers"), "providers")
    providers = {
        _non_empty_str(name, "providers anahtarı"): _provider(name, value)
        for name, value in providers_raw.items()
        if not name.startswith(_NOTE_PREFIX)
    }
    if not providers:
        raise WebSelectorsError("web-selectors.json: hiç sağlayıcı tanımı yok.")
    upload = _mapping(root.get("gemini_upload"), "gemini_upload")
    _reject_unknown(upload, {"menu_trigger", "option"}, "gemini_upload")
    option = _mapping(root.get("model_option"), "model_option")
    _reject_unknown(option, {"gemini_web", "default"}, "model_option")
    return WebSelectors(
        providers=providers,
        schema_version=str(root["version"]),
        bundle_digest=hashlib.sha256(
            json.dumps(raw, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest(),
        gemini_upload_menu_trigger=_non_empty_str(
            upload.get("menu_trigger"), "gemini_upload.menu_trigger"
        ),
        gemini_upload_option=_non_empty_str(upload.get("option"), "gemini_upload.option"),
        model_option_gemini=_non_empty_str(option.get("gemini_web"), "model_option.gemini_web"),
        model_option_default=_non_empty_str(option.get("default"), "model_option.default"),
        challenge_dom=_selector_list(root.get("challenge_dom"), "challenge_dom", required=True),
    )


@cache
def web_selectors() -> WebSelectors:
    """Pakete gömülü seçici dosyasını bir kez oku ve doğrula."""
    resource = resources.files(_RESOURCE_PACKAGE).joinpath(*_RESOURCE_PATH)
    try:
        raw = json.loads(resource.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise WebSelectorsError(f"web-selectors.json okunamadı: {error}") from error
    return parse_web_selectors(raw)


def _provider(name: str, value: object) -> ProviderSelectors:
    where = f"providers.{name}"
    fields = _mapping(value, where)
    _reject_unknown(fields, {*_REQUIRED_LISTS, *_OPTIONAL_LISTS}, where)
    lists = {
        key: _selector_list(
            fields.get(key, [] if key in _OPTIONAL_LISTS else None),
            f"{where}.{key}",
            required=key in _REQUIRED_LISTS,
        )
        for key in (*_REQUIRED_LISTS, *_OPTIONAL_LISTS)
    }
    if set(lists["origin_roles"]) - ASSISTANT_ROLE_EVIDENCE:
        raise WebSelectorsError("Bilinmeyen assistant köken attribute ilişkisi.")
    if set(lists["origin_ids"]) - {"id", "data-content-search-unit-key"}:
        raise WebSelectorsError("Köken kimliği attribute allowlist dışında.")
    return ProviderSelectors(**lists)


def _mapping(value: object, where: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise WebSelectorsError(f"web-selectors.json: {where} bir nesne olmalı.")
    return value


def _reject_unknown(data: Mapping[str, object], allowed: set[str], where: str = "kök") -> None:
    unknown = sorted(key for key in data if key not in allowed and not key.startswith(_NOTE_PREFIX))
    if unknown:
        raise WebSelectorsError(f"web-selectors.json: {where} içinde bilinmeyen anahtar: {unknown}")


def _non_empty_str(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WebSelectorsError(f"web-selectors.json: {where} boş olmayan bir metin olmalı.")
    return value


def _selector_list(value: object, where: str, *, required: bool) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise WebSelectorsError(f"web-selectors.json: {where} bir liste olmalı.")
    items = tuple(_non_empty_str(item, where) for item in value)
    if required and not items:
        raise WebSelectorsError(f"web-selectors.json: {where} boş olamaz.")
    return items
