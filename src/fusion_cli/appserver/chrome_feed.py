"""Uygulama teli satırlarını Chrome yan panelinin anlayacağı kısa öğelere çevirir.

Yan panel Claude in Chrome gibi çalışır: kullanıcı ne olduğunu adım adım görür
("instagram.com açıldı", "“Kampanyalar” tıklandı", "Sayfa aşağı kaydırıldı").
Motorun olayları masaüstü içindir ve ham araç argümanları taşır; burada yalnız
panelin gösterdiği alanlar, insan diliyle üretilir. Tanınmayan satır `None` olur.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

#: Adım metnindeki alıntıların üst sınırı; panel dar bir sütundur.
MAX_QUOTE = 60
#: Başarısız adımın gösterilen hata özeti.
MAX_ERROR = 160


def panel_item(line: str) -> dict[str, Any] | None:
    """Tek bir tel satırını panel öğesine çevir; ilgisizse `None`."""
    try:
        message = json.loads(line)
    except ValueError:
        return None
    if not isinstance(message, dict):
        return None
    data = message.get("veri")
    if not isinstance(data, dict):
        return None
    if message.get("tip") == "soru" and isinstance(message.get("id"), str):
        return {"tur": "soru", "id": message["id"], "veri": data}
    if message.get("tip") != "olay":
        return None
    event = data.get("olay")
    if event == "ModelCallStarted" and not data.get("background"):
        return {"tur": "dusunuyor"}
    if event == "ErrorOccurred":
        return {"tur": "hata", "metin": str(data.get("message", ""))[:MAX_ERROR]}
    if event == "ToolExecuted" and str(data.get("name", "")) in _VISIBLE_TOOLS:
        return _step(data)
    return None


_VISIBLE_TOOLS = frozenset(
    {
        "chrome_page",
        "chrome_action",
        "chrome_click",
        "chrome_type",
        "chrome_navigate",
        "read_file",
        "write_file",
        "edit_file",
        "multi_edit",
        "run_shell",
        "ask_teacher",
    }
)


#: Panelde "Ekran / Fare / Klavye" olarak görünen denetim kanalları.
_ACTION_CHANNELS = {
    "screenshot": "ekran",
    "click_at": "fare",
    "double_click": "fare",
    "triple_click": "fare",
    "type_focused": "klavye",
    "zoom": "ekran",
    "right_click": "fare",
    "drag": "fare",
    "wheel": "fare",
    "hover": "fare",
    "scroll": "fare",
    "key": "klavye",
}


def control_channel(name: str, args: Mapping[str, Any]) -> str | None:
    """Adımın hangi denetim kanalına girdiği; okuma/gezinme adımlarında `None`."""
    if name == "chrome_click":
        return "fare"
    if name == "chrome_type":
        return "klavye"
    if name == "chrome_action":
        return _ACTION_CHANNELS.get(str(args.get("action")))
    return None


def _step(data: Mapping[str, Any]) -> dict[str, Any]:
    name = str(data.get("name", ""))
    raw_args = data.get("args")
    args: Mapping[str, Any] = raw_args if isinstance(raw_args, Mapping) else {}
    outcome = str(data.get("outcome", "ok"))
    output = str(data.get("output", ""))
    item: dict[str, Any] = {
        "tur": "adim",
        "arac": name,
        "metin": step_text(name, args, output),
        "durum": outcome,
    }
    detail = step_detail(name, args, output)
    if detail:
        item["ayrinti"] = detail
    channel = control_channel(name, args)
    if channel:
        item["kanal"] = channel
    if outcome == "failed":
        item["hata"] = output[:MAX_ERROR]
    return item


MAX_DETAIL = 200


def step_detail(name: str, args: Mapping[str, Any], output: str = "") -> str:
    """Adım satırının açılır ayrıntısı: hedef adres, bulunan öğe, sayfa başlığı.

    Parola/kart alanına yazılan metin ASLA gösterilmez ya da kaydedilmez.
    """
    parts: list[str] = []
    if name == "chrome_navigate" and isinstance(args.get("url"), str):
        parts.append(str(args["url"]))
    if name == "chrome_action" and args.get("action") == "open" and args.get("value"):
        parts.append(str(args["value"]))
    for field in ("title", "name", "label", "url"):
        value = _output_field(output, field)
        if value and value not in parts:
            parts.append(value)
    if name == "chrome_type":
        field = _output_field(output, "name") or _output_field(output, "label")
        parts = [f"Alan: {field}"] if field else []
    text = " · ".join(" ".join(part.split()) for part in parts)
    return text if len(text) <= MAX_DETAIL else text[: MAX_DETAIL - 1] + "…"


def step_text(name: str, args: Mapping[str, Any], output: str = "") -> str:
    """Aracın ne yaptığını tek kısa cümleyle söyle."""
    if name == "ask_teacher":
        return "Öğretmene danışıldı"
    if name == "run_shell":
        return "Proje komutu çalıştırıldı"
    if name in {"read_file", "write_file", "edit_file", "multi_edit"}:
        action = {
            "read_file": "okundu",
            "write_file": "yazıldı",
            "edit_file": "düzenlendi",
            "multi_edit": "düzenlendi",
        }[name]
        return f"{_quote(args.get('path')) or 'Dosya'} {action}"
    if name == "chrome_navigate":
        return f"{_host(args.get('url'))} açıldı"
    if name == "chrome_page":
        query = args.get("query")
        return f"“{_quote(query)}” arandı" if isinstance(query, str) and query else "Sayfa okundu"
    if name == "chrome_click":
        clicked = _output_field(output, "name")
        return f"“{_quote(clicked)}” tıklandı" if clicked else "Öğeye tıklandı"
    if name == "chrome_type":
        return f"“{_quote(args.get('text'))}” yazıldı"
    if name == "chrome_action":
        return _action_text(args)
    return "Tarayıcıda işlem yapıldı"


def _action_text(args: Mapping[str, Any]) -> str:
    action = args.get("action")
    value = args.get("value")
    if action == "scroll":
        return "Sayfa yukarı kaydırıldı" if value == "up" else "Sayfa aşağı kaydırıldı"
    if action == "wait":
        return f"“{_quote(value)}” bekleniyor"
    if action == "key":
        return f"{_quote(value) or 'Enter'} tuşuna basıldı"
    if action == "screenshot":
        return "Ekran görüntüsü alındı"
    if action == "tabs":
        return "Sekmeler listelendi"
    if action == "open":
        return f"{_host(value)} yeni sekmede açıldı"
    if action == "tab":
        return "Başka sekmeye geçildi"
    if action == "select":
        return f"“{_quote(value)}” seçildi"
    return _ACTION_TEXTS.get(str(action), "Tarayıcıda işlem yapıldı")


_ACTION_TEXTS = {
    "back": "Geri gidildi",
    "forward": "İleri gidildi",
    "reload": "Sayfa yenilendi",
    "close": "Sekme kapatıldı",
    "hover": "Öğenin üzerine gelindi",
    "text": "Sayfanın tamamı okundu",
    "click_at": "Ekrandaki noktaya tıklandı",
    "double_click": "Çift tıklandı",
    "triple_click": "Üç kez tıklandı",
    "type_focused": "Odaktaki alana yazıldı",
    "check": "Onay kutusu ayarlandı",
    "resize": "Pencere yeniden boyutlandı",
    "zoom": "Ekranın bir bölgesi büyütüldü",
    "right_click": "Sağ tıklandı",
    "drag": "Öğe sürüklenip bırakıldı",
    "wheel": "Fare tekerleği çevrildi",
}


def _host(url: object) -> str:
    text = str(url or "").strip()
    host = urlsplit(text if "://" in text else f"https://{text}").hostname or text
    return host.removeprefix("www.")[:MAX_QUOTE] or "Sayfa"


def _quote(value: object) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= MAX_QUOTE else text[: MAX_QUOTE - 1] + "…"


def _output_field(output: str, field: str) -> str:
    try:
        parsed = json.loads(output)
    except ValueError:
        return ""
    value = parsed.get(field) if isinstance(parsed, dict) else None
    return value if isinstance(value, str) else ""
