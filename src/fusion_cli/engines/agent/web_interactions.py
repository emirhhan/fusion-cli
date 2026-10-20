"""Statik web çıktısında hiçbir eyleme bağlanmamış düğmeleri bul."""

from __future__ import annotations

from html.parser import HTMLParser

_NATIVE_ACTIONS = frozenset({"popovertarget", "commandfor"})


class _InteractionParser(HTMLParser):
    """Yorumları ve öznitelik içindeki ``>`` işaretini HTML kurallarıyla ayır."""

    def __init__(self) -> None:
        super().__init__()
        self.document = False
        self.script = False
        self.form_depth = 0
        self.inert_count = 0
        self.empty_form_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"html", "body"}:
            self.document = True
        if tag == "script":
            self.script = True
        if tag == "form":
            self.form_depth += 1
            attributes = {name.casefold(): value for name, value in attrs}
            if (attributes.get("action") or "").strip() == "#" and not any(
                name.startswith(("on", "hx-", "x-on", "@")) for name in attributes
            ):
                self.empty_form_count += 1
        if tag != "button":
            return

        attributes = {name.casefold(): value for name, value in attrs}
        names = attributes.keys()
        if "disabled" in names or any(name in _NATIVE_ACTIONS for name in names):
            return
        if any(name.startswith(("on", "hx-", "x-on", "@")) for name in names):
            return
        kind = (attributes.get("type") or "").casefold()
        if (self.form_depth or "form" in names) and kind in {"", "submit", "reset"}:
            return
        self.inert_count += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self.form_depth = max(0, self.form_depth - 1)


def inert_buttons(html: str, javascript: str) -> tuple[str, ...]:
    """JS'siz tam sayfadaki gerçek eylemi olmayan ``button`` öğelerini bildir.

    JavaScript kaynağı veya ``script`` etiketi varsa olay işleyicisi statik
    dosyadan kesin bilinemediği için bu dar kural uygulanmaz.
    """
    if javascript.strip():
        return ()
    parser = _InteractionParser()
    parser.feed(html)
    parser.close()
    if parser.script or not parser.document or not parser.inert_count:
        return ()
    return (
        f"{parser.inert_count} eylemsiz düğme var: statik sayfada bu düğmelerin "
        "form, JavaScript veya yerel tarayıcı eylemi yok. Gerçek hedefe bağlantı "
        "ver ya da çalışan bir eylem bağla; boş bağlantıyı yalnız düğmeye çevirme.",
    )


def empty_form_actions(html: str, javascript: str) -> tuple[str, ...]:
    """JS'siz tam sayfada yalnız ``#`` hedefine gönderilen formları bul."""
    if javascript.strip():
        return ()
    parser = _InteractionParser()
    parser.feed(html)
    parser.close()
    if parser.script or not parser.document or not parser.empty_form_count:
        return ()
    return (
        f'{parser.empty_form_count} form action="#" ile gönderiliyor: gönderim '
        "gerçek bir alıcıya ulaşmıyor. Çalışan bir uç nokta veya istemci tarafı "
        "gönderim akışı kur; alıcı yoksa formu çalışan bir iletişim bağlantısıyla değiştir.",
    )
