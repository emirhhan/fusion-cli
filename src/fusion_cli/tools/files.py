"""Dosya araçları: okuma, yazma, düzenleme, listeleme.

Düzenleme araçlarının ortak kuralı: `old` metni dosyada BİREBİR ve BENZERSİZ
eşleşmelidir. Belirsiz eşleşme sessizce ilk bulunana uygulanmaz — reddedilir ve
modelden daha fazla bağlam istenir. Yanlış yere yapılan bir düzenleme, yapılmayan
bir düzenlemeden çok daha pahalıdır.

`multi_edit` ATOMİKTİR: tüm değişiklikler bellekte uygulanır, hepsi başarılıysa dosya
tek seferde yazılır. Yarım uygulanmış dosya bırakmaz.
"""

from __future__ import annotations

import re
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

    ham = path.read_bytes()
    data = ham[:MAX_READ_BYTES]
    kirpildi = len(ham) > MAX_READ_BYTES
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return ToolResult.failure(f"Metin dosyası değil (UTF-8 çözülemedi): {path}")

    lines = text.splitlines()
    if not lines:
        return ToolResult("(boş dosya)")
    numbered = "\n".join(f"{index:>5}\t{line}" for index, line in enumerate(lines, 1))
    if kirpildi:
        # Sessiz kırpma modele "dosyanın tamamını okudum" yanılgısı verir; sonra
        # göremediği bir yeri düzenlemeye kalkar.
        numbered += (
            f"\n\n[… dosya {MAX_READ_BYTES} bayttan büyük olduğu için KIRPILDI; "
            "gerisi gösterilmedi. Aramak için search_code kullan.]"
        )
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
    replace_all = args.get("replace_all") is True

    if not path.exists():
        return ToolResult.failure(f"Dosya yok: {path}")
    text = path.read_text(encoding="utf-8")

    if replace_all:
        # Tekrar eden aynı metni tek çağrıda düzeltmek için. Benzersizlik şartı
        # olmadan çalışır ama METİN VAR OLMALIDIR: sessizce hiçbir şey yapmamak,
        # modele "düzelttim" yanılgısı verir.
        count = text.count(old)
        if count == 0:
            return ToolResult.failure(_NOT_FOUND)
        path.write_text(text.replace(old, new), encoding="utf-8")
        context.touched.add(path)
        return ToolResult(f"düzenlendi: {path} ({count} değişiklik)")

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
    toplam = 0
    for position, (old, new, replace_all) in enumerate(edits, 1):
        if replace_all:
            count = working.count(old)
            if count == 0:
                # Atomiklik: tek bir düzenleme tutmazsa dosyaya HİÇ dokunulmaz.
                return ToolResult.failure(f"{position}. düzenleme: {_NOT_FOUND}")
            working = working.replace(old, new)
            toplam += count
            continue
        problem = _match_problem(working, old, position=position)
        if problem is not None:
            return ToolResult.failure(problem)
        working = working.replace(old, new, 1)
        toplam += 1

    path.write_text(working, encoding="utf-8")
    context.touched.add(path)
    return ToolResult(f"düzenlendi: {path} ({toplam} değişiklik uygulandı)")


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


def parse_edits(raw: object) -> tuple[tuple[str, str, bool], ...]:
    """`edits` listesini (old, new, replace_all) üçlülerine çevir; bozuksa hata ver."""
    if not isinstance(raw, list):
        raise ArgumentError("'edits' bir liste olmalı.")
    edits: list[tuple[str, str, bool]] = []
    for position, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise ArgumentError(f"{position}. düzenleme bir sözlük olmalı: {{'old':…, 'new':…}}")
        old, new = item.get("old"), item.get("new")
        if not isinstance(old, str) or not old:
            raise ArgumentError(f"{position}. düzenleme: 'old' boş olmayan bir metin olmalı.")
        if not isinstance(new, str):
            raise ArgumentError(f"{position}. düzenleme: 'new' metin olmalı.")
        edits.append((old, new, item.get("replace_all") is True))
    return tuple(edits)


def _neden_eslesmedi(text: str, old: str) -> str:
    """Eşleşme neden tutmadı? Sebebi söylemek, "bulunamadı" demekten çok daha yararlı.

    Dört koşuluk kayıtta EN SIK araç hatası buydu. Muhtemel sebep bir araç tuzağı:
    `read_file` her satıra "    12\t" biçiminde numara ekliyor ve modelin bunu
    ayıklaması gerektiğini kimse söylemiyordu.
    """
    if _LINE_NUMBERED.search(old):
        return (
            "'old' metni satır numarası içeriyor. read_file çıktısındaki '   12\t' "
            "önekini ve sekmeyi ayıkla; yalnızca satırın KENDİSİNİ gönder."
        )
    # Boşluk farkı: metin dosyada var ama girinti/boşluk düzeni tutmuyor.
    sikistir = " ".join(old.split())
    if sikistir and sikistir in " ".join(text.split()):
        return (
            "'old' metni dosyada var ama GİRİNTİ/boşluk düzeni farklı. Satırı "
            "read_file çıktısından birebir kopyala (baştaki boşluklar dahil)."
        )
    return _NOT_FOUND


#: read_file'ın eklediği satır numarası öneki: boşluklar + sayı + sekme.
_LINE_NUMBERED = re.compile(r"^\s*\d+\t", re.M)

#: Eşleşme bulunamadığında modele dönen açıklama.
_NOT_FOUND = (
    "'old' metni dosyada bulunamadı. Birebir eşleşmeli — önce dosyayı okuyup metni "
    "oradan kopyala."
)


def _match_problem(text: str, old: str, *, position: int | None) -> str | None:
    """`old` benzersiz eşleşiyor mu? Eşleşmiyorsa modele ne yapacağını söyle."""
    count = text.count(old)
    if count == 1:
        return None
    prefix = f"{position}. düzenleme: " if position is not None else ""
    if count == 0:
        return f"{prefix}{_neden_eslesmedi(text, old)}"
    return (
        f"{prefix}'old' metni {count} kez geçiyor; benzersiz olmalı. HEPSİNİ aynı "
        'şekilde değiştirecekseniz replace_all: true ekleyin — tek çağrıda biter. '
        "Yalnızca birini değiştirecekseniz çevresinden birkaç satır daha ekleyerek "
        "eşleşmeyi daraltın."
    )
