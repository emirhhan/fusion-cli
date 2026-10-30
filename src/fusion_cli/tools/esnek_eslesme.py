"""Hoşgörülü düzenleme eşleşmesi: tam eşleşme yokken TEK ve belirsiz olmayan satır bloğu.

Neden var: Aider'ın düzenleme biçimi ölçümünde (SEARCH/REPLACE blokları), eşleşme
boşluk/girinti farkına takılan bloklar için esnek eşleşme eklenince düzenleme hataları
yaklaşık 9 kat azaldı. Aynı sınıf hata burada da var: model `read_file` çıktısını
yeniden yazarken satır sonu boşluğunu, girintiyi (sekme/boşluk) ya da CRLF'yi kaybediyor;
düzenleme "bulunamadı" diye reddediliyor ve tur yanıyor (bkz. `_neden_eslesmedi`).

Kural muhafazakârdır — yanlış yere yapılan düzenleme, yapılmayan düzenlemeden pahalıdır:

- Yalnız `old` satırlarının TAMAMI, dosyada ardışık satırlarla boşluk farkları dışında
  eşleşiyorsa (satır içeriği `strip` sonrası aynı, göreli girinti aynı) uygulanır.
- Eşleşen blok TEK olmalıdır. Birden çok ya da sıfır eşleşmede `None` döner; çağıran bugünkü
  teşhis mesajıyla reddeder.
- `new` metninin girintisi dosyadaki gerçek girintiye uyarlanır (ortak kayma + sekme/boşluk
  stili), böylece düzenleme dosyaya yabancı girintiyle yazılmaz.
- `replace_all` ile birlikte kullanılmaz (çağıran tarafın sorumluluğu).
"""

from __future__ import annotations

from dataclasses import dataclass

#: Sekme genişliği. Sekmeli ve boşluklu girinti bu genişlikle karşılaştırılır.
TAB_WIDTH = 4

#: Tolere edilen farkın modele söylenen adları (sonuç satırında kullanılır).
DIFF_TRAILING_WHITESPACE = "satır sonu boşluğu"
DIFF_INDENT = "girinti"
DIFF_LINE_ENDING = "satır sonu (CRLF)"


@dataclass(frozen=True, slots=True)
class FlexibleEdit:
    """Esnek eşleşmeyle uygulanmış tek bir düzenleme."""

    #: Düzenleme uygulanmış TÜM metin.
    updated: str
    #: Değişen bloğun ilk ve son satırı (1 tabanlı, düzenleme ÖNCESİ metinde).
    first_line: int
    last_line: int
    #: Tolere edilen farklar (`DIFF_*`), tekrarsız ve sabit sırada.
    differences: tuple[str, ...]


def _indent_width(line: str) -> int:
    """Satırın görsel girinti genişliği (sekme `TAB_WIDTH` sütun sayılır)."""
    expanded = line.expandtabs(TAB_WIDTH)
    return len(expanded) - len(expanded.lstrip(" "))


def _leading(line: str) -> str:
    return line[: len(line) - len(line.lstrip(" \t"))]


def _is_blank(line: str) -> bool:
    return not line.strip()


def _window_delta(file_lines: list[str], old_lines: list[str]) -> int | None:
    """Pencere `old_lines` ile eşleşiyorsa sabit girinti farkı; eşleşmiyorsa `None`.

    Boş satırlar içerik olarak aynı sayılır ve farka katılmaz. Boş olmayan her satırda
    içerik (`strip` sonrası) aynı ve girinti farkı AYNI olmalıdır: göreli girinti bozulmuşsa
    (ör. iç içe blok düzleşmişse) bu başka bir kod demektir ve eşleşme reddedilir.
    """
    delta: int | None = None
    for file_line, old_line in zip(file_lines, old_lines, strict=True):
        if _is_blank(file_line) or _is_blank(old_line):
            if _is_blank(file_line) != _is_blank(old_line):
                return None
            continue
        if file_line.strip() != old_line.strip():
            return None
        line_delta = _indent_width(file_line) - _indent_width(old_line)
        if delta is None:
            delta = line_delta
        elif delta != line_delta:
            return None
    return 0 if delta is None else delta


def _find_unique_window(file_lines: list[str], old_lines: list[str]) -> tuple[int, int] | None:
    """Tek eşleşen pencerenin (başlangıç dizini, girinti farkı); aksi halde `None`."""
    size = len(old_lines)
    found: list[tuple[int, int]] = []
    for start in range(len(file_lines) - size + 1):
        delta = _window_delta(file_lines[start : start + size], old_lines)
        if delta is not None:
            found.append((start, delta))
            if len(found) > 1:
                return None
    return found[0] if found else None


def _indent_string(width: int, *, use_tabs: bool) -> str:
    """`width` sütunluk girintiyi dosyanın stilinde (sekme ya da boşluk) üret."""
    if width <= 0:
        return ""
    if use_tabs:
        return "\t" * (width // TAB_WIDTH) + " " * (width % TAB_WIDTH)
    return " " * width


def _adapt_new_lines(
    new_lines: list[str], file_block: list[str], old_lines: list[str], delta: int
) -> list[str]:
    """`new` satırlarını dosyadaki gerçek girintiye uyarla.

    `old` ile `new` modelin AYNI girinti çerçevesindedir; dosyadaki blok bu çerçeveden
    `delta` sütun kayıktır ve farklı bir karakter (sekme/boşluk) kullanıyor olabilir.
    Girinti zaten birebir aynıysa `new` olduğu gibi bırakılır (gereksiz yeniden
    biçimlendirme yok).
    """
    identical = all(
        _leading(file_line) == _leading(old_line)
        for file_line, old_line in zip(file_block, old_lines, strict=True)
        if not _is_blank(file_line) and not _is_blank(old_line)
    )
    if identical:
        return new_lines
    use_tabs = any("\t" in _leading(line) for line in file_block if not _is_blank(line))
    adapted: list[str] = []
    for line in new_lines:
        if _is_blank(line):
            adapted.append(line.rstrip(" \t"))
            continue
        width = max(_indent_width(line) + delta, 0)
        adapted.append(_indent_string(width, use_tabs=use_tabs) + line.lstrip(" \t"))
    return adapted


def _differences(
    file_block: list[str], old_lines: list[str], *, had_crlf: bool, delta: int
) -> tuple[str, ...]:
    """Tolere edilen farkların adları (modele açıkça söylenir)."""
    found: list[str] = []
    pairs = [(f, o) for f, o in zip(file_block, old_lines, strict=True) if not _is_blank(f)]
    if any(len(f) - len(f.rstrip()) != len(o) - len(o.rstrip()) for f, o in pairs):
        found.append(DIFF_TRAILING_WHITESPACE)
    if delta != 0 or any(_leading(f) != _leading(o) for f, o in pairs):
        found.append(DIFF_INDENT)
    if had_crlf:
        found.append(DIFF_LINE_ENDING)
    return tuple(found)


def apply_flexible(text: str, old: str, new: str) -> FlexibleEdit | None:
    """`old`'u boşluk farklarını tolere ederek TEK yerde `new` ile değiştir.

    `text` evrensel satır sonuyla okunmuş (`\\n`) dosya metnidir. Tek ve belirsiz olmayan
    eşleşme yoksa `None` döner; çağıran tam eşleşme hatasını aynen modele verir.
    """
    had_crlf = "\r\n" in old or "\r\n" in new
    old_text = old.replace("\r\n", "\n")
    new_text = new.replace("\r\n", "\n")
    # Sondaki satır sonu iki tarafta da varsa ikisinden de atılır (bloğun kendisi satır
    # düzeyinde eşleşir); yalnız birinde varsa anlam kayması olur — tahmin etme.
    if old_text.endswith("\n"):
        if not new_text.endswith("\n"):
            return None
        old_text, new_text = old_text[:-1], new_text[:-1]
    if not old_text.strip():
        return None
    old_lines = old_text.split("\n")
    file_lines = text.split("\n")
    window = _find_unique_window(file_lines, old_lines)
    if window is None:
        return None
    start, delta = window
    end = start + len(old_lines)
    file_block = file_lines[start:end]
    new_lines = _adapt_new_lines(new_text.split("\n"), file_block, old_lines, delta)
    updated = "\n".join([*file_lines[:start], *new_lines, *file_lines[end:]])
    return FlexibleEdit(
        updated=updated,
        first_line=start + 1,
        last_line=end,
        differences=_differences(file_block, old_lines, had_crlf=had_crlf, delta=delta),
    )


def describe(edit: FlexibleEdit) -> str:
    """Modele giden tek cümle: ne tolere edildi, hangi satırlar."""
    farklar = " ve ".join(edit.differences) if edit.differences else "boşluk"
    span = (
        f"satır {edit.first_line}"
        if edit.first_line == edit.last_line
        else f"satır {edit.first_line}-{edit.last_line}"
    )
    return f"tam eşleşme yoktu; {farklar} farkı tolere edildi, {span}"
