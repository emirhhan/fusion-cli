"""Fusion'ın KENDİ yazdığı, kullanıcının düzenleyebildiği düz metin otomatik bellek (P-036).

Claude Code'un `~/.claude/projects/<proje>/memory/MEMORY.md` düzeninin Fusion karşılığı:
bir **indeks** (`BELLEK.md`) ve altında **konu dosyaları** (`konular/<konu>.md`). İndeksin
ilk 200 satırı / 25 KB'ı her turun sistem istemine girer; konu dosyaları yalnız model
`memory_read` ile istediğinde okunur. Ders belleği (ChromaDB, `lessons.py`) ile çift kayıt
yoktur: buraya yazılan bir ders DEĞİL, projeye/kullanıcıya dair kalıcı bilgidir ve
kullanıcı dosyayı düz metin olarak açıp düzenleyebilir.

Dört koruma: yazılan her metin `redact` ile maskelenir (sır/e-posta kalıcı dosyaya girmesin),
içerikteki `<otomatik_bellek` etiketleri etkisizleştirilir (bloktan kaçış yok), konu adı
yol kaçışına kapalı bir kısa ada indirilir ve yazılan yol SINIR dizinin (`boundary`: proje
kökü ya da bellek dizini) içinde kalır — aradaki hiçbir bileşen sembolik bağ olamaz.
Ölçüldü (31 Ekim): klonlanan depodaki `.fusion/ajan-bellek/<ad>/konular/<konu>.md -> ~/.zshrc`
bağını `remember` (onaysız araç) izleyip hedefi eziyordu. Dizin yazmaları kilit altındadır.

Aynı sınıf alt ajan belleği için de kullanılır (P-055): `PlainMemory(dizin)` dizine göre
parametreliktir; ajan belleği `agent_memory_dir` ile başka bir dizine açılır.
"""

from __future__ import annotations

import re
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path

from ..config.models import Config
from ..core.errors import FusionError
from ..core.redaction import redact

#: İndeks dosyası ve konu klasörü adı.
INDEX_FILE = "BELLEK.md"
TOPIC_DIR = "konular"
#: Sistem istemine giren indeks payı (Claude Code ile aynı: 200 satır / 25 KB).
PROMPT_MAX_LINES = 200
PROMPT_MAX_BYTES = 25_000
#: Tek bir yazmanın en fazla karakteri; daha uzunu kırpılır (bellek not defteridir, arşiv değil).
ENTRY_MAX_CHARS = 2_000
#: `memory_read` ile tek seferde dönen en fazla karakter.
READ_MAX_CHARS = 12_000
#: Bellek bloğunun etiketi; içerikte geçen kopyalar etkisizleştirilir.
BLOCK_TAG = "otomatik_bellek"
#: İndekste konu bağlantılarının toplandığı başlık ve serbest notların başlığı.
TOPICS_HEADER = "## Konular"
NOTES_HEADER = "## Notlar"
#: Yeni indeksin ilk satırı: kullanıcı dosyayı açınca ne olduğunu anlasın.
_INDEX_PREAMBLE = (
    "# Fusion belleği\n\n"
    "Fusion'ın bu proje için kendi yazdığı kalıcı notlar. İlk 200 satır her turun bağlamına "
    "girer; dosyayı düzenleyebilir, satır silebilirsin. Konu ayrıntıları `konular/` altında.\n"
)
#: Alt ajan belleği kapsamları (P-055); dizinler `agent_memory` modülünde (Claude Code yolları).
AGENT_MEMORY_SCOPES = ("user", "project", "local")

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_TR_MAP = str.maketrans("çğıöşüâîû", "cgiosuaiu")


class PlainMemoryError(FusionError):
    """Düz metin belleğe yazılamadı ya da okunamadı (geçersiz konu, dosya hatası)."""


@dataclass(frozen=True, slots=True)
class MemoryWrite:
    """Bir yazmanın sonucu: hangi dosyaya, kaç satır oldu."""

    path: Path
    created: bool
    lines: int


@dataclass(frozen=True, slots=True)
class MemoryStatus:
    """`/memory` ve masaüstü panelinin gösterdiği durum."""

    directory: Path
    index_lines: int
    index_bytes: int
    #: İndeksin istem payını aşan kısmı var mı (200 satır / 25 KB)?
    truncated: bool
    topics: tuple[str, ...]


def project_slug(root: Path) -> str:
    """Proje kökünü dizin adına çevir (Claude Code kuralı: harf-rakam dışı her şey `-`)."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(root.resolve()))


def topic_slug(topic: str) -> str:
    """Konu adını dosya adına indir: `Ödeme Akışı` → `odeme-akisi`. Boşsa hata."""
    lowered = topic.strip().lower().translate(_TR_MAP)
    slug = _SLUG_RE.sub("-", lowered).strip("-")[:64]
    if not slug:
        raise PlainMemoryError("Konu adı boş ya da yalnız noktalama içeriyor.")
    return slug


def project_memory_dir(config: Config, root: Path) -> Path:
    """Projenin otomatik bellek dizini: `runtime.auto_memory_dir` doluysa o, yoksa
    `<bellek>/projeler/<slug>/bellek` (Claude'un `autoMemoryDirectory` karşılığı)."""
    override = str(getattr(config.runtime, "auto_memory_dir", "") or "").strip()
    if override:
        return Path(override).expanduser()
    return config.memory_dir / "projeler" / project_slug(root) / "bellek"


def agent_memory_dir(
    config: Config, root: Path, agent: str, scope: str, *, home: Path | None = None
) -> Path | None:
    """Alt ajan belleğinin Claude Code dizini (#24); bkz. `agent_memory`."""
    from .agent_memory import agent_memory_dir as _claude_dir

    return _claude_dir(config, root, agent, scope, home=home)


def open_agent_memory(
    config: Config, root: Path, agent: str, scope: str, *, home: Path | None = None
) -> PlainMemory | None:
    """Alt ajanın kalıcı belleği (P-055, #24): kapsam geçersizse None.

    `local` kapsam git'e girmez: ilk yazmada `.claude/agent-memory-local/.gitignore` (`*`)
    oluşur. Blok etiketi `ajan:<ad>` olur ki model kimin notu olduğunu görsün. Eski Fusion
    dizinindeki bellek ilk açılışta bir kez kopyalanır.
    """
    from .agent_memory import AGENT_INDEX_FILE, legacy_agent_memory_dir, migrate_legacy

    directory = agent_memory_dir(config, root, agent, scope, home=home)
    if directory is None:
        return None
    migrate_legacy(legacy_agent_memory_dir(config, root, agent, scope), directory)
    # Proje kapsamında sınır proje kökü (depodan gelen bağ dışarı çıkaramaz), kullanıcı
    # kapsamında `~/.claude`.
    boundary = directory.parent.parent if scope == "user" else root
    return PlainMemory(
        directory,
        label=f"ajan:{agent}",
        ignore_parent_in_git=scope == "local",
        boundary=boundary,
        index_name=AGENT_INDEX_FILE,
    )


def build_plain_memory(config: Config, root: Path) -> PlainMemory | None:
    """`runtime.auto_memory` açıksa projenin belleği, kapalıysa None (araç hiç sunulmaz)."""
    if not getattr(config.runtime, "auto_memory", True):
        return None
    directory = project_memory_dir(config, root)
    override = str(getattr(config.runtime, "auto_memory_dir", "") or "").strip()
    return PlainMemory(directory, boundary=directory if override else config.memory_dir)


def _neutralize_tags(content: str) -> str:
    return re.sub(rf"<(/?)\s*{BLOCK_TAG}", r"‹\1" + BLOCK_TAG, content, flags=re.IGNORECASE)


def _clean_entry(text: str) -> str:
    """Tek bir yazmayı belleğe uygun hale getir: maskele, etiketi etkisizleştir, kırp."""
    cleaned = _neutralize_tags(redact(text.strip()))
    if len(cleaned) > ENTRY_MAX_CHARS:
        cleaned = cleaned[:ENTRY_MAX_CHARS] + " […kırpıldı]"
    return cleaned


class PlainMemory:
    """Bir dizindeki `BELLEK.md` + `konular/*.md`. Dosya yoksa ilk yazmada oluşur."""

    def __init__(
        self,
        directory: Path,
        *,
        label: str = "proje",
        ignore_parent_in_git: bool = False,
        boundary: Path | None = None,
        index_name: str = INDEX_FILE,
    ) -> None:
        self.directory = directory
        #: İndeks dosyasının adı: proje belleği `BELLEK.md`, ajan belleği `MEMORY.md` (#24).
        self.index_name = index_name
        #: Blokta görünen kaynak etiketi (`proje` ya da alt ajan adı).
        self.label = label
        #: İlk yazmada üst dizine `*` içeren `.gitignore` koy (yerel ajan belleği).
        self._ignore_parent_in_git = ignore_parent_in_git
        #: Yazmaların dışına çıkamayacağı güvenilir dizin; verilmezse bellek dizininin üstü
        #: (`.gitignore` işareti oraya yazılır).
        self._boundary = (boundary if boundary is not None else directory.parent).absolute()
        self._lock = threading.Lock()

    @property
    def index_path(self) -> Path:
        return self.directory / self.index_name

    @property
    def topic_dir(self) -> Path:
        return self.directory / TOPIC_DIR

    def exists(self) -> bool:
        return self.index_path.is_file()

    # ------------------------------------------------------------------ okuma

    def topics(self) -> tuple[str, ...]:
        if not self.topic_dir.is_dir():
            return ()
        return tuple(sorted(path.stem for path in self.topic_dir.glob("*.md")))

    def status(self) -> MemoryStatus:
        text = self._read_text(self.index_path)
        lines = text.splitlines()
        size = len(text.encode("utf-8"))
        return MemoryStatus(
            directory=self.directory,
            index_lines=len(lines),
            index_bytes=size,
            truncated=len(lines) > PROMPT_MAX_LINES or size > PROMPT_MAX_BYTES,
            topics=self.topics(),
        )

    def read(self, topic: str = "") -> str:
        """İndeksi (konu boşsa) ya da bir konu dosyasını oku; yoksa boş metin."""
        path = self.index_path if not topic.strip() else self.topic_dir / f"{topic_slug(topic)}.md"
        text = self._read_text(path)
        if len(text) > READ_MAX_CHARS:
            return text[:READ_MAX_CHARS] + "\n[…kırpıldı…]"
        return text

    def prompt_block(self) -> str:
        """Sistem istemine girecek blok: indeksin ilk 200 satırı / 25 KB, maskeli."""
        text = self._read_text(self.index_path)
        guide = self._agent_guide()
        if not text.strip():
            if not guide:
                return ""
            return (
                f'<{BLOCK_TAG} kaynak="{self.label}" dosya="{self.index_name}">\n'
                f"{guide.strip()}\n</{BLOCK_TAG}>"
            )
        head, truncated = _head(text, PROMPT_MAX_LINES, PROMPT_MAX_BYTES)
        body = _neutralize_tags(redact(head))
        suffix = (
            f"\n[…indeks kırpıldı; tamamı için memory_read çağır ya da {self.index_name} kısalt…]"
            if truncated
            else ""
        )
        topics = ", ".join(self.topics())
        topic_line = f"\nKonu dosyaları (memory_read ile): {topics}" if topics else ""
        return (
            f'<{BLOCK_TAG} kaynak="{self.label}" dosya="{self.index_name}">\n'
            f"{body}{suffix}{topic_line}{guide}\n</{BLOCK_TAG}>"
        )

    def _agent_guide(self) -> str:
        """Ajan belleğinde dizin yolu: Claude Code'daki gibi Read/Write/Edit ile yönetilir (#24)."""
        if not self.label.startswith("ajan:"):
            return ""
        return (
            f"\nBellek dizini: {self.directory} — {self.index_name} ve konu dosyalarını "
            "Read/Write/Edit ile oku ve güncelle."
        )

    # ------------------------------------------------------------------ yazma

    def remember(self, topic: str, text: str) -> MemoryWrite:
        """Konu dosyasına bir madde ekle ve indeksin konu listesinde bağlantısını tut."""
        slug = topic_slug(topic)
        entry = _clean_entry(text)
        if not entry:
            raise PlainMemoryError("Hatırlanacak metin boş.")
        with self._lock:
            path = self.topic_dir / f"{slug}.md"
            created = not path.is_file()
            self._ensure_index()
            self._append(path, f"# {slug}\n\n" if created else "", f"- {entry}\n")
            self._link_topic(slug, entry)
            return MemoryWrite(path=path, created=created, lines=_line_count(path))

    def note(self, text: str) -> MemoryWrite:
        """`## Notlar` bölümüne tek satır ekle (`#` kısayolu); satır sonları boşluğa iner."""
        entry = " ".join(_clean_entry(text).split())
        if not entry:
            raise PlainMemoryError("Not boş.")
        with self._lock:
            created = not self.index_path.is_file()
            self._ensure_index()
            content = self._read_text(self.index_path)
            if NOTES_HEADER not in content:
                content = content.rstrip("\n") + f"\n\n{NOTES_HEADER}\n"
            content = content.rstrip("\n") + f"\n- {entry}\n"
            self._write(self.index_path, content)
            return MemoryWrite(
                path=self.index_path, created=created, lines=_line_count(self.index_path)
            )

    def import_markdown(self, source_dir: Path, *, source: str) -> int:
        """Başka bir aracın bellek dizinini (`MEMORY.md` + konu `.md`'leri) içe aktar.

        İndeks dosyası `## <kaynak>'dan içe aktarıldı` başlığı altına eklenir; diğer `.md`
        dosyaları aynı adla yoksa konu olarak kopyalanır. Döndürülen sayı alınan dosya adedi.
        Sembolik bağ izlenmez; içerik maskelenir.
        """
        if not source_dir.is_dir():
            return 0
        taken = 0
        with self._lock:
            for path in sorted(source_dir.glob("*.md")):
                if path.is_symlink():
                    continue
                text = self._read_text(path)
                if not text.strip():
                    continue
                cleaned = _neutralize_tags(redact(text))
                if path.name.upper() in {"MEMORY.MD", INDEX_FILE.upper()}:
                    self._ensure_index()
                    header = f"\n## {source}'dan içe aktarıldı ({path.name})\n"
                    self._append(self.index_path, "", header + cleaned + "\n")
                    taken += 1
                    continue
                target = self.topic_dir / f"{topic_slug(path.stem)}.md"
                if target.is_file():
                    continue
                self._ensure_index()
                self._write(target, cleaned if cleaned.endswith("\n") else cleaned + "\n")
                self._link_topic(target.stem, f"{source}'dan içe aktarıldı")
                taken += 1
        return taken

    def write_index(self, text: str) -> None:
        """İndeksi kullanıcının verdiği metinle değiştir (masaüstü düzenleyici).

        Kullanıcının kendi yazısı maskelenMEZ: dosya onun; ama bloktan kaçış etiketi yine
        etkisizleştirilir çünkü metin her turun istemine girer.
        """
        with self._lock:
            self._write(self.index_path, _neutralize_tags(text))

    def clear(self) -> bool:
        """Bu belleğin tamamını sil (alt ajan belleğini sıfırlamak için). Yoksa False."""
        with self._lock:
            if not self.directory.is_dir():
                return False
            self._guard(self.index_path)
            try:
                shutil.rmtree(self.directory)
            except OSError as error:
                raise PlainMemoryError(f"Bellek silinemedi: {error}") from error
            return True

    # ------------------------------------------------------------------ iç

    def _ensure_index(self) -> None:
        if self.index_path.is_file():
            return
        if self._ignore_parent_in_git:
            marker = self.directory.parent / ".gitignore"
            if not marker.is_file():
                self._write(marker, "*\n")
        self._write(self.index_path, _INDEX_PREAMBLE + f"\n{TOPICS_HEADER}\n")

    def _link_topic(self, slug: str, hint: str) -> None:
        content = self._read_text(self.index_path)
        link = f"[{slug}]({TOPIC_DIR}/{slug}.md)"
        if link in content:
            return
        line = f"- {link} — {_first_words(hint)}"
        if TOPICS_HEADER in content:
            head, _, tail = content.partition(TOPICS_HEADER)
            # Konular başlığından sonraki ilk boş satıra (ya da bir sonraki başlığa) kadar liste.
            tail_lines = tail.split("\n")
            insert_at = 1
            while insert_at < len(tail_lines) and tail_lines[insert_at].startswith("- "):
                insert_at += 1
            tail_lines.insert(insert_at, line)
            content = head + TOPICS_HEADER + "\n".join(tail_lines)
        else:
            content = content.rstrip("\n") + f"\n\n{TOPICS_HEADER}\n{line}\n"
        self._write(self.index_path, content)

    def _append(self, path: Path, header: str, line: str) -> None:
        existing = self._read_text(path) if path.is_file() else ""
        body = header or existing
        if body and not body.endswith("\n"):
            body += "\n"
        self._write(path, body + line)

    def _write(self, path: Path, content: str) -> None:
        self._guard(path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except OSError as error:
            raise PlainMemoryError(f"Bellek dosyası yazılamadı ({path.name}): {error}") from error

    def _guard(self, path: Path) -> None:
        """Yol sınır dizinin içinde kalsın: aradaki hiçbir bileşen sembolik bağ olmasın ve
        çözülmüş hali sınırın altında dursun. Depodan gelen bağ (git sembolik bağ saklar)
        onaysız `remember` çağrısıyla kök dışı dosya ezememeli."""
        target = path.absolute()
        for candidate in (target, *target.parents):
            if candidate == self._boundary:
                break
            if candidate.is_symlink():
                raise PlainMemoryError(
                    f"Bellek yolu sembolik bağ içeriyor, yazılmadı: {candidate.name}"
                )
        else:
            raise PlainMemoryError(f"Bellek yolu sınır dizinin dışında: {target.name}")
        try:
            target.resolve().relative_to(self._boundary.resolve())
        except ValueError as error:
            raise PlainMemoryError(
                f"Bellek dizini sınır dışına çözülüyor, yazılmadı: {target.name}"
            ) from error

    @staticmethod
    def _read_text(path: Path) -> str:
        try:
            if path.is_symlink() or not path.is_file():
                return ""
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return ""


def _head(text: str, max_lines: int, max_bytes: int) -> tuple[str, bool]:
    lines = text.splitlines()
    head = "\n".join(lines[:max_lines])
    truncated = len(lines) > max_lines
    encoded = head.encode("utf-8")
    if len(encoded) > max_bytes:
        head = encoded[:max_bytes].decode("utf-8", errors="ignore")
        truncated = True
    return head, truncated


def _line_count(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8").splitlines())
    except OSError:
        return 0


def _first_words(text: str, limit: int = 80) -> str:
    first = " ".join(text.split())
    return first if len(first) <= limit else first[: limit - 1] + "…"
