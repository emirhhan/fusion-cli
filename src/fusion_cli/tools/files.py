"""Dosya araçları: okuma, yazma, düzenleme, listeleme.

Düzenleme araçlarının ortak kuralı: `old` metni dosyada BİREBİR ve BENZERSİZ
eşleşmelidir. Belirsiz eşleşme sessizce ilk bulunana uygulanmaz — reddedilir ve
modelden daha fazla bağlam istenir. Yanlış yere yapılan bir düzenleme, yapılmayan
bir düzenlemeden çok daha pahalıdır.

`multi_edit` ATOMİKTİR: tüm değişiklikler bellekte uygulanır, hepsi başarılıysa dosya
tek seferde yazılır. Yarım uygulanmış dosya bırakmaz.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from ..core.constants import (
    MAX_DIR_ENTRIES,
    MAX_READ_BYTES,
    MAX_READ_LINES,
    VISIBLE_DOTFILES,
)
from ..core.errors import PathAccessError
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import (
    ArgumentError,
    optional_str,
    require_list,
    require_positive_int,
    require_str,
    require_text,
)


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
    # İzinli alan: kök + kullanıcının `--add-dir` ile AÇIKÇA verdiği dizinler.
    izinli = (root, *(extra.resolve() for extra in context.extra_roots))
    # Var olmayan hedefte de doğrulama yapılabilmesi için strict=False.
    concrete = resolved.resolve()
    if not any(concrete == izin or izin in concrete.parents for izin in izinli):
        raise PathAccessError(f"Kısıtlı kipte proje kökü dışına erişilemez: {raw} (kök: {root})")
    return concrete


def atomic_write(path: Path, content: str) -> None:
    """Geçici dosyaya yaz, sonra yerine taşı.

    `write_text` doğrudan hedefe yazar: süreç yazmanın ortasında ölürse kullanıcının
    çalışan dosyası yarım kalır. `os.replace` aynı dosya sisteminde atomiktir, bu
    yüzden geçici dosya HEDEFLE AYNI DİZİNDE açılır — /tmp başka bir bağlama noktası
    olabilir ve taşıma atomikliğini kaybederdi (`config.writer` aynı deseni kullanır).
    """
    handle, name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    gecici = Path(name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as dosya:
            dosya.write(content)
        gecici.replace(path)
    except BaseException:
        gecici.unlink(missing_ok=True)
        raise


def display_path(context: ToolContext, path: Path) -> str:
    """Yolu KULLANICIYA gösterilecek biçime çevir: kök altındaysa göreli.

    Ölçüldü: hata satırı `Dosya yok: /private/var/folders/m0/4p1xq…/tmpb5c/
    ayarlar.json. Y…` biçiminde basılıyordu. Sonuç satırının neredeyse tamamını
    gürültülü mutlak yol yiyor, mesajın asıl açıklaması ("Yolu list_dir ile
    doğrula…") kesiliyordu — yani kullanıcı hatanın NEDENİNİ göremiyordu.

    Kök dışındaki yol mutlak kalır: orada tam yol gerçekten bilgidir, kullanıcı
    çalışma alanının dışına çıkıldığını görmelidir.
    """
    for root in (context.root, context.root.resolve()):
        # Kök İKİ biçimiyle de denenir: `resolve_path` sonucu çözümlenmiş yoldur
        # ve macOS'ta `/var` → `/private/var` olur. Yalnızca ham köke bakmak, kök
        # altındaki her yolu "dışarıda" sayıp mutlak bırakıyordu.
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        return str(relative) if relative.parts else "."
    return str(path)


def read_file(args: ToolArgs, context: ToolContext) -> ToolResult:
    path = resolve_path(context, require_str(args, "path"))
    if not path.exists():
        # Çıkışsız hata mesajı kilitlenme üretir: model ne yapacağını bilemez ve
        # aynı çağrıyı tekrarlar. Her engelleme yasal bir sonraki hamle göstermeli.
        return ToolResult.failure(
            f"Dosya yok: {display_path(context, path)}. Yolu list_dir ya da glob ile doğrula; "
            "dosyanın oluşturulması gerekiyorsa write_file kullan."
        )
    if path.is_dir():
        return ToolResult.failure(f"Bu bir dizin, dosya değil: {display_path(context, path)}")

    ham = path.read_bytes()
    data = ham[:MAX_READ_BYTES]
    kirpildi = len(ham) > MAX_READ_BYTES
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return ToolResult.failure(
            f"Metin dosyası değil (UTF-8 çözülemedi): {display_path(context, path)}"
        )

    lines = text.splitlines()
    if not lines:
        return ToolResult("(boş dosya)")

    offset = require_positive_int(args, "offset", default=1)
    limit = require_positive_int(args, "limit", default=MAX_READ_LINES)
    if offset > len(lines):
        return ToolResult.failure(
            f"{display_path(context, path)} yalnızca {len(lines)} satır; offset={offset} "
            f"dosyanın sonunu geçiyor. offset 1 ile {len(lines)} arasında olmalı."
        )

    pencere = lines[offset - 1 : offset - 1 + limit]
    son = offset + len(pencere) - 1
    numbered = "\n".join(
        f"{index:>5}\t{line}" for index, line in enumerate(pencere, offset)
    )
    kalan = len(lines) - son
    if kirpildi or kalan > 0:
        # Sessiz kırpma modele "dosyanın tamamını okudum" yanılgısı verir; sonra
        # göremediği bir yeri düzenlemeye kalkar.
        #
        # Not SIRADAKİ ÇAĞRIYI BİREBİR YAZAR. Ölçüldü: eski not yalnızca "gerisi
        # gösterilmedi, search_code kullan" diyordu. Model devam etmek istedi,
        # devam etmenin bir yolu olmadığı için AYNI çağrıyı tekrarladı, birebir
        # aynı içeriği aldı ve turu "ne yapmamı istiyorsunuz" diye bitirdi.
        # Kullanıcının görevi ortadayken. Çıkışı olmayan sınır kilitlenme üretir.
        numbered += f"\n\n{_devam_notu(display_path(context, path), son, kalan, kirpildi)}"
    if not kirpildi and offset == 1 and kalan == 0:
        context.fully_read.add(path)
    return ToolResult(numbered)


def _devam_notu(path: str, son: int, kalan: int, kirpildi: bool) -> str:
    """Kırpmayı ve SIRADAKİ çağrıyı yaz."""
    if kirpildi and kalan <= 0:
        return (
            f"[… dosya {MAX_READ_BYTES} bayttan büyük olduğu için KIRPILDI; gerisi "
            "gösterilmedi. İlgili yeri bulmak için search_code kullan.]"
        )
    return (
        f"[… {son}. satırda kesildi, {kalan} satır daha var. Devamı için: "
        f'read_file {{"path": "{path}", "offset": {son + 1}}} '
        "— aynı çağrıyı offset'siz TEKRARLAMA, aynı satırları geri alırsın.]"
    )


def write_file(args: ToolArgs, context: ToolContext) -> ToolResult:
    kurtarma = _kurtarma(args, context)
    if kurtarma is not None:
        return kurtarma

    path = resolve_path(context, require_str(args, "path"))
    if "content" in args:
        content = require_text(args, "content")
        context.pending.take()  # eski saklanan içerik ASLA kullanılmaz
    else:
        # Saklanan içerik BİR KEZ kullanılır; sonraki çağrıya sızmamalı.
        content = context.pending.take()
        if not content:
            return ToolResult.failure(
                "'content' alanı eksik ve saklanmış içerik de yok. Dosyanın tam içeriğini gönder."
            )

    existed = path.exists()
    # Bu turda agent'ın KENDİ oluşturduğu dosya "okunmuş" sayılır: kaybedilecek,
    # görülmemiş bir satırı yoktur. Aksi halde iskele kurup doldurma akışı kilitlenir
    # (`scaffold_web` dosyayı yazar, doldurma toptan yazmadır, kapı onu bloklar) ve
    # tur ilerleme üretmeden ölür — ölçülen gerçek hata buydu.
    kendi_olusturdu = context.changes.was_created_this_turn(path)
    if existed and not kendi_olusturdu and path not in context.fully_read:
        # `read_file` açıklaması zaten "değiştirmeden ÖNCE mutlaka oku" diyor; burada
        # o kural UYGULANIR. Tam içeriğini görmediğin bir dosyayı baştan yazmak,
        # görmediğin kısmı silmek demektir — kırpılmış okumada bu sessiz veri kaybıdır.
        return ToolResult.failure(
            f"Bu dosya var ve tam içeriğini okumadın: {display_path(context, path)}. "
            "Üzerine yazmak "
            "görmediğin satırları siler. Kısmi değişiklik için edit_file kullan; "
            "gerçekten tamamını yenileyeceksen önce read_file ile TAMAMINI oku."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    context.changes.record(path)
    try:
        atomic_write(path, content)
    except OSError as exc:
        return ToolResult.failure(f"Yazılamadı: {display_path(context, path)} ({exc})")
    context.touched.add(path)
    action = "güncellendi" if existed else "oluşturuldu"
    return ToolResult(f"{action}: {display_path(context, path)} ({len(content)} karakter)")


def _kurtarma(args: ToolArgs, context: ToolContext) -> ToolResult | None:
    """`path` eksik ama içerik varsa içeriği sakla ve yalnızca yolu iste.

    Beş koşuda 14 kez yaşandı: model büyük içeriği yazıp sondaki küçük `path` alanını
    hiç üretmiyor. Eskiden içerik çöpe gidiyor ve model 15 KB'ı baştan üretiyordu.
    Artık içerik saklanıyor; model tek satırlık bir çağrıyla işi bitiriyor.

    Yol TAHMİN EDİLMEZ — yanlış tahmin var olan bir dosyanın üzerine yazmak demektir.
    """
    if "path" in args and str(args.get("path") or "").strip():
        return None
    icerik = args.get("content")
    if not isinstance(icerik, str) or not icerik:
        return None
    context.pending.content = icerik
    return ToolResult.failure(
        f"'path' alanı eksik. İçeriğini SAKLADIM ({len(icerik)} karakter); tekrar "
        "gönderme. Aynı aracı YALNIZCA path vererek çağır: "
        '{"path": "dizin/dosya.uzanti"}'
    )


def edit_file(args: ToolArgs, context: ToolContext) -> ToolResult:
    path = resolve_path(context, require_str(args, "path"))
    old = require_str(args, "old")
    new = require_text(args, "new")
    replace_all = args.get("replace_all") is True

    if not path.exists():
        return ToolResult.failure(
            f"Dosya yok: {display_path(context, path)}. Düzenlenecek bir dosya yok — "
            "içeriği write_file ile oluştur, ya da doğru yolu list_dir / glob ile bul."
        )
    text = path.read_text(encoding="utf-8")

    if replace_all:
        # Tekrar eden aynı metni tek çağrıda düzeltmek için. Benzersizlik şartı
        # olmadan çalışır ama METİN VAR OLMALIDIR: sessizce hiçbir şey yapmamak,
        # modele "düzelttim" yanılgısı verir.
        count = text.count(old)
        if count == 0:
            return ToolResult.failure(_NOT_FOUND)
        context.changes.record(path)
        atomic_write(path, text.replace(old, new))
        context.touched.add(path)
        return ToolResult(f"düzenlendi: {display_path(context, path)} ({count} değişiklik)")

    problem = _match_problem(text, old, position=None)
    if problem is not None:
        return ToolResult.failure(problem)

    context.changes.record(path)
    atomic_write(path, text.replace(old, new, 1))
    context.touched.add(path)
    return ToolResult(f"düzenlendi: {display_path(context, path)} (1 değişiklik)")


def multi_edit(args: ToolArgs, context: ToolContext) -> ToolResult:
    path = resolve_path(context, require_str(args, "path"))
    edits = parse_edits(require_list(args, "edits"))

    if not path.exists():
        return ToolResult.failure(
            f"Dosya yok: {display_path(context, path)}. Düzenlenecek bir dosya yok — "
            "içeriği write_file ile oluştur, ya da doğru yolu list_dir / glob ile bul."
        )
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

    context.changes.record(path)
    atomic_write(path, working)
    context.touched.add(path)
    return ToolResult(f"düzenlendi: {display_path(context, path)} ({toplam} değişiklik uygulandı)")


def list_dir(args: ToolArgs, context: ToolContext) -> ToolResult:
    path = resolve_path(context, optional_str(args, "path", "."))
    if not path.exists():
        return ToolResult.failure(f"Yol yok: {display_path(context, path)}")
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
    "'old' metni dosyada bulunamadı. Birebir eşleşmeli — önce dosyayı okuyup metni oradan kopyala."
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
        "şekilde değiştirecekseniz replace_all: true ekleyin — tek çağrıda biter. "
        "Yalnızca birini değiştirecekseniz çevresinden birkaç satır daha ekleyerek "
        "eşleşmeyi daraltın."
    )
