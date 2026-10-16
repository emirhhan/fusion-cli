"""Boş görsel kaynakları; JavaScript ile doldurulan kaynak için kesin hata iddiası yok."""

from html.parser import HTMLParser


class _Images(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.empty = 0
        self.template_depth = 0
        self.has_script = False
        self.picture_sources: list[bool] = []
        self.picture_fallbacks = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "template":
            self.template_depth += 1
        if self.template_depth:
            return
        if tag == "script":
            self.has_script = True
        if tag == "picture":
            self.picture_sources.append(False)
        if tag == "source" and self.picture_sources and (dict(attrs).get("srcset") or "").strip():
            self.picture_sources[-1] = True
        if tag == "img":
            values = dict(attrs)
            if not (values.get("src") or "").strip() and not (values.get("srcset") or "").strip():
                if self.picture_sources and self.picture_sources[-1]:
                    self.picture_fallbacks += 1
                else:
                    self.empty += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "template" and self.template_depth:
            self.template_depth -= 1
        elif tag == "picture" and not self.template_depth and self.picture_sources:
            self.picture_sources.pop()


def empty_images(html: str, js: str) -> tuple[list[str], list[str]]:
    """Statik boş kaynak engel; olası hydration ise tarayıcı doğrulaması uyarısı."""
    parser = _Images()
    parser.feed(html)
    warnings = (
        [
            "picture görselinin boş img yedeği var; "
            "source/media eşleşmesini hedef viewportlarda doğrula."
        ]
        if parser.picture_fallbacks
        else []
    )
    if not parser.empty:
        return [], warnings
    message = (
        f"{parser.empty} boş görsel kaynağı var: img için src/srcset doldur. "
        "JavaScript dolduruyorsa yükleme sonrasında gerçek tarayıcıda görselin "
        "açıldığını doğrula; yer tutucuyu teslim edilmiş görsel sayma."
    )
    return ([], [*warnings, message]) if parser.has_script or js.strip() else ([message], warnings)
