"""Dosya araçları: okuma, yazma, düzenleme, listeleme.

Düzenleme araçlarının ortak kuralı: `old` metni dosyada BİREBİR ve BENZERSİZ
eşleşmelidir. Belirsiz eşleşme sessizce ilk bulunana uygulanmaz — reddedilir ve
modelden daha fazla bağlam istenir. Yanlış yere yapılan bir düzenleme, yapılmayan
bir düzenlemeden çok daha pahalıdır.

`multi_edit` ATOMİKTİR: tüm değişiklikler bellekte uygulanır, hepsi başarılıysa dosya
tek seferde yazılır. Yarım uygulanmış dosya bırakmaz.
"""

from __future__ import annotations

from pathlib import Path

from ..core.constants import MAX_DIR_ENTRIES, MAX_READ_BYTES, VISIBLE_DOTFILES
from ..core.errors import PathAccessError
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import ArgumentError, optional_str, require_list, require_str, require_text


def resolve_path(context: ToolContext, raw: str) -> Path:
    """Kullanıcı/model yolunu çözümle: `~` açılır, göreli yol köke bağlanır.

    `context.restrict_to_root` açıksa yol kök altında olmak zorundadır: sembolik
    linkler çözülür (`resolve`) ve sonuç köke bağlı değilse `PathAccessError`
    fırlatılır. Böylece `..` ile dışarı taşma ve köke sızdıran symlink engellenir.
    """
    path = Path(raw).expanduser()
    resolved = path if path.is_absolute() else context.root / path
    if not context.restrict_to_root:
        return resolved
    root = context.root.resolve()
    # Var olmayan hedefte de doğrulama yapılabilmesi için strict=False.
    concrete = resolved.resolve()
    if concrete != root and root not in concrete.parents:
        raise PathAccessError(
            f"Kısıtlı kipte proje kökü dışına erişilemez: {raw} (kök: {root})"
        )
    return concrete


def read_file(args: ToolArgs, context: ToolContext) -> ToolResult:
    path = resolve_path(context, require_str(args, "path"))
    if not path.exists():
        return ToolResult.failure(f"Dosya yok: {path}")
    if path.is_dir():
        return ToolResult.failure(f"Bu bir dizin, dosya değil: {path}")

    data = path.read_bytes()[:MAX_READ_BYTES]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return ToolResult.failure(f"Metin dosyası değil (UTF-8 çözülemedi): {path}")

    lines = text.splitlines()
    if not lines:
        return ToolResult("(boş dosya)")
    numbered = "\n".join(f"{index:>5}\t{line}" for index, line in enumerate(lines, 1))
    return ToolResult(numbered)


def write_file(args: ToolArgs, context: ToolContext) -> ToolResult:
    path = resolve_path(context, require_str(args, "path"))
    content = require_text(args, "content")

    existed = path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    context.touched.add(path)
    action = "güncellendi" if existed else "oluşturuldu"
    return ToolResult(f"{action}: {path} ({len(content)} karakter)")


def edit_file(args: ToolArgs, context: ToolContext) -> ToolResult:
    path = resolve_path(context, require_str(args, "path"))
    old = require_str(args, "old")
    new = require_text(args, "new")

    if not path.exists():
        return ToolResult.failure(f"Dosya yok: {path}")
    text = path.read_text(encoding="utf-8")

    problem = _match_problem(text, old, position=None)
    if problem is not None:
        return ToolResult.failure(problem)

    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    context.touched.add(path)
    return ToolResult(f"düzenlendi: {path} (1 değişiklik)")


def multi_edit(args: ToolArgs, context: ToolContext) -> ToolResult:
    path = resolve_path(context, require_str(args, "path"))
    edits = parse_edits(require_list(args, "edits"))

    if not path.exists():
        return ToolResult.failure(f"Dosya yok: {path}")
    original = path.read_text(encoding="utf-8")

    working = original
    for position, (old, new) in enumerate(edits, 1):
        problem = _match_problem(working, old, position=position)
        if problem is not None:
            # Atomiklik: tek bir düzenleme tutmazsa dosyaya HİÇ dokunulmaz.
            return ToolResult.failure(problem)
        working = working.replace(old, new, 1)

    path.write_text(working, encoding="utf-8")
    context.touched.add(path)
    return ToolResult(f"düzenlendi: {path} ({len(edits)} değişiklik uygulandı)")


def list_dir(args: ToolArgs, context: ToolContext) -> ToolResult:
    path = resolve_path(context, optional_str(args, "path", "."))
    if not path.exists():
        return ToolResult.failure(f"Yol yok: {path}")
    if path.is_file():
        return ToolResult(str(path))

    entries = sorted(path.iterdir(), key=lambda entry: (entry.is_file(), entry.name.lower()))
    visible = [
        f"{'📁' if entry.is_dir() else '📄'} {entry.name}"
        for entry in entries[:MAX_DIR_ENTRIES]
        if not entry.name.startswith(".") or entry.name in VISIBLE_DOTFILES
    ]
    return ToolResult("\n".join(visible) if visible else "(boş dizin)")


# --------------------------------------------------------------------------- #


def parse_edits(raw: object) -> tuple[tuple[str, str], ...]:
    """`edits` listesini (old, new) çiftlerine çevir; biçim bozuksa hata ver."""
    if not isinstance(raw, list):
        raise ArgumentError("'edits' bir liste olmalı.")
    edits: list[tuple[str, str]] = []
    for position, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise ArgumentError(f"{position}. düzenleme bir sözlük olmalı: {{'old':…, 'new':…}}")
        old, new = item.get("old"), item.get("new")
        if not isinstance(old, str) or not old:
            raise ArgumentError(f"{position}. düzenleme: 'old' boş olmayan bir metin olmalı.")
        if not isinstance(new, str):
            raise ArgumentError(f"{position}. düzenleme: 'new' metin olmalı.")
        edits.append((old, new))
    return tuple(edits)


def _match_problem(text: str, old: str, *, position: int | None) -> str | None:
    """`old` benzersiz eşleşiyor mu? Eşleşmiyorsa modele ne yapacağını söyle."""
    count = text.count(old)
    if count == 1:
        return None
    prefix = f"{position}. düzenleme: " if position is not None else ""
    if count == 0:
        return (
            f"{prefix}'old' metni dosyada bulunamadı. Birebir eşleşmeli — "
            "önce dosyayı okuyup metni oradan kopyala."
        )
    return (
        f"{prefix}'old' metni {count} kez geçiyor; benzersiz olmalı. "
        "Çevresinden birkaç satır daha ekleyerek eşleşmeyi daralt."
    )
