"""REPL önekleri (P-022): `!` kabuk, `@dosya` anma, `#` bellek notu.

Claude Code'un etkileşimli kipi örnek alınmıştır:

- `! komut` — komut DOĞRUDAN çalışır (model çağrılmaz); çıktı ekrana basılır ve bir
  sonraki turun sistem bağlamına "kullanıcının çalıştırdığı kabuk çıktısı" olarak girer.
  Çalıştırma `tools.shell.run_shell` üzerinden yapılır: silme çöpe gider, ezilen dosya
  geri alma kaydına girer, uydurma yol reddedilir — modelin kullandığı güvencelerin aynısı.
  Plan kipinde komut çalışmaz (plan = hiçbir değişiklik yok).
- `@yol` — mesajın içindeki dosya anmaları: dosya içeriği (sınırlı) bir sonraki turun
  bağlamına eklenir, mesaj metni olduğu gibi kalır. Yol kök/ek köklere göre çözülür;
  `restrict_to_root` açıksa kök dışı reddedilir. `@sunucu:kaynak` MCP kaynak biçimi
  tanınır ama köprüde `resources/read` olmadığı için şimdilik açık bir notla reddedilir.
- `# not` — kalıcı bellek notu: düz metin otomatik belleğin (`BELLEK.md`, P-036) `## Notlar`
  bölümüne yazılır; model sonraki turlarda okur, `/memory edit` ile düzenlenir. Bellek
  kapalıyken satır yutulmaz, olağan mesaj olarak modele gider.

Öneklerin ayrıştırılması SAFTIR (test edilebilir); yan etkiler `run_shell_prefix`,
`expand_mentions`, `add_memory_note` içindedir ve iki REPL yüzeyi (satır-içi, tam-ekran)
aynı fonksiyonları çağırır.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path

from ...core.changeset import ChangeSet
from ...core.constants import MAX_OUTPUT_CHARS
from ...core.errors import FusionError
from ...core.redaction import redact
from ...core.tools import ToolContext
from ...engines.agent.approval import ApprovalMode
from ...memory.plain_memory import PlainMemoryError
from ...ui import messages
from .state import ReplState

#: Bir anılan dosyadan bağlama alınacak en fazla karakter.
MENTION_MAX_CHARS = 20_000
#: Tek mesajda en fazla kaç dosya anması işlenir.
MENTION_MAX_FILES = 8
#: `# not` tek satır ve en çok bu kadar karakterdir; ötesi düz mesajdır.
MEMORY_NOTE_MAX_CHARS = 500
#: Bir turda bekleyen `!`/`@` bloklarının toplam üst sınırı; aşılırsa en eskisi düşer.
PENDING_CONTEXT_MAX_CHARS = 3 * MAX_OUTPUT_CHARS
#: `@` anması: boşluk ya da satır başından sonra `@`, ardından boşluksuz yol.
#: E-posta adresleri (`ad@alan`) eşleşmez: `@` öncesinde karakter yoktur.
_MENTION = re.compile(r"(?:(?<=\s)|^)@([^\s@]+)")
#: MCP kaynak biçimi: `sunucu:kaynak` (iki nokta, yol ayracı yok).
_RESOURCE = re.compile(r"^([A-Za-z0-9_-]+):(.+)$")
#: Dosya adlarının sonunda kalan noktalama (cümle sonu).
_TRAILING_PUNCT = ".,;:!?)»\"'"


def shell_command(line: str) -> str | None:
    """`! komut` satırının komutu; önek değilse None. `!!` ya da `!=` gibi yazımlar mesajdır.

    Ölçüldü (31 Ekim): çok satırlı girdi (`!ls\\nrm x`) tek komut sayılıyordu; önekler TEK
    satırlıktır, çok satır düz mesajdır.
    """
    if not line.startswith("!") or len(line) < 2 or "\n" in line.strip():
        return None
    if line[1] in "!=":
        return None
    command = line[1:].strip()
    return command or None


def memory_note(line: str) -> str | None:
    """`# not` satırının notu; önek değilse None. `#!` (shebang) ve `#1234` biçimleri mesajdır.

    Ölçüldü (31 Ekim): `# Görev\\nşunu yap` gibi Markdown başlıklı yapıştırma model
    çağrılmadan kalıcı derse yazılıyordu. Not tek satır ve `MEMORY_NOTE_MAX_CHARS` ile sınırlı.
    """
    if not line.startswith("#") or len(line) < 2 or line.startswith("##"):
        return None
    body = line[1:]
    if not body[0].isspace():
        return None
    note = body.strip()
    # `# # başlık` gibi yazımlar da Markdown'dır, not değil.
    if not note or note.startswith("#") or "\n" in note or len(note) > MEMORY_NOTE_MAX_CHARS:
        return None
    return note


def pending_memory_note(state: ReplState, line: str) -> str | None:
    """Satır belleğe gidecek `# not` mu? Bellek KAPALIYKEN None: satır olağan istemdir.

    Üç yüzey (satır-içi, tam-ekran, masaüstü) bu kapıyı ve `add_memory_note`'u paylaşır.
    """
    if state.plain_memory is None:
        return None
    return memory_note(line)


@dataclass(frozen=True, slots=True)
class Mention:
    """Mesajdaki tek bir `@` anması."""

    raw: str
    #: `sunucu:kaynak` biçimindeyse sunucu adı; dosyaysa boş.
    server: str = ""
    resource: str = ""

    @property
    def is_resource(self) -> bool:
        return bool(self.server)


def mentions(line: str) -> tuple[Mention, ...]:
    """Satırdaki `@` anmaları (sıra korunur, tekrar elenir)."""
    found: list[Mention] = []
    seen: set[str] = set()
    for match in _MENTION.finditer(line):
        raw = match.group(1).rstrip(_TRAILING_PUNCT)
        if not raw or raw in seen:
            continue
        seen.add(raw)
        resource = _RESOURCE.match(raw)
        # Windows sürücü harfi (`C:\…`) ya da `./x` kaynak sayılmaz; yol ayracı içeren
        # ya da tek harfli önek dosyadır.
        if resource and "/" not in resource.group(1) and len(resource.group(1)) > 1:
            found.append(Mention(raw, server=resource.group(1), resource=resource.group(2)))
        else:
            found.append(Mention(raw))
    return tuple(found)


@dataclass(frozen=True, slots=True)
class MentionResult:
    """Anmaların çözümü: bağlama girecek bloklar ve kullanıcıya gösterilecek notlar."""

    blocks: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


def expand_mentions(line: str, state: ReplState) -> MentionResult:
    """`@yol` anmalarını oku ve bağlam bloklarına çevir. Mesaj metni DEĞİŞMEZ."""
    from ...tools.files import display_path, resolve_path

    found = mentions(line)
    if not found:
        return MentionResult()
    context = ToolContext(
        root=state.root,
        extra_roots=state.extra_roots,
        restrict_to_root=state.config.runtime.restrict_to_root,
    )
    blocks: list[str] = []
    notes: list[str] = []
    for mention in found[:MENTION_MAX_FILES]:
        if mention.is_resource:
            # Okuma turda, MCP bağlandıktan sonra yapılır (`mcp_bridge.reference_service`; P-049).
            known = any(server.name == mention.server for server in state.config.mcp_servers)
            template = (
                messages.MENTION_RESOURCE_QUEUED if known else messages.MENTION_RESOURCE_UNSUPPORTED
            )
            notes.append(template.format(raw=mention.raw, server=mention.server))
            continue
        try:
            path = resolve_path(context, mention.raw)
        except FusionError as error:
            notes.append(messages.MENTION_UNREADABLE.format(raw=mention.raw, error=error))
            continue
        # `@dataclass`, `@property`: yol ayracı ve uzantısı olmayan, var olmayan sözcük bir
        # dekoratördür; "okunamadı" gürültüsü üretmeden geçilir (31 Ekim).
        if not path.exists() and _looks_like_word(mention.raw):
            continue
        block = _read_block(path, display_path(context, path))
        if block is None:
            notes.append(
                messages.MENTION_UNREADABLE.format(raw=mention.raw, error=messages.MENTION_NOT_FILE)
            )
            continue
        blocks.append(block)
        notes.append(messages.MENTION_ADDED.format(path=display_path(context, path)))
    if len(found) > MENTION_MAX_FILES:
        notes.append(messages.MENTION_TOO_MANY.format(limit=MENTION_MAX_FILES))
    return MentionResult(tuple(blocks), tuple(notes))


def _looks_like_word(raw: str) -> bool:
    return "/" not in raw and "." not in raw and "\\" not in raw


def _read_block(path: Path, label: str) -> str | None:
    if path.is_dir():
        try:
            entries = sorted(
                entry.name + ("/" if entry.is_dir() else "") for entry in path.iterdir()
            )
        except OSError:
            return None
        listing = "\n".join(entries[:200])
        return messages.MENTION_DIR_BLOCK.format(path=label, listing=redact(listing))
    if not path.is_file():
        return None
    # Dosyanın tamamı belleğe alınmaz: `MENTION_MAX_CHARS + 1` karakter okunur (GB'lık log).
    try:
        with path.open(encoding="utf-8") as handle:
            text = handle.read(MENTION_MAX_CHARS + 1)
    except (OSError, UnicodeDecodeError):
        return None
    truncated = len(text) > MENTION_MAX_CHARS
    if truncated:
        text = text[:MENTION_MAX_CHARS]
    note = messages.MENTION_TRUNCATED.format(limit=MENTION_MAX_CHARS) if truncated else ""
    # Sırlar maskeli: anılan `.env` ya da günlük dosyası anahtarı modele taşımasın.
    return messages.MENTION_FILE_BLOCK.format(path=label, text=redact(text), note=note)


def push_pending_context(state: ReplState, block: str) -> None:
    """Bloğu bekleyen bağlama ekle; toplam `PENDING_CONTEXT_MAX_CHARS`'ı aşarsa en eskisi düşer."""
    blocks = [*state.pending_blocks, block]
    while len(blocks) > 1 and sum(len(item) for item in blocks) > PENDING_CONTEXT_MAX_CHARS:
        blocks.pop(0)
    state.pending_blocks = blocks


@dataclass(frozen=True, slots=True)
class ShellPrefixResult:
    """`!` komutunun sonucu: ekrana basılacak çıktı + bağlama girecek blok."""

    output: str
    ok: bool
    context_block: str = ""
    notes: tuple[str, ...] = field(default=())


async def run_shell_prefix(state: ReplState, command: str) -> ShellPrefixResult:
    """`! komut` — `run_shell` aracıyla çalıştır; çıktıyı sonraki tura bağlam yap."""
    if state.approval is ApprovalMode.PLAN:
        return ShellPrefixResult("", False, notes=(messages.SHELL_PREFIX_PLAN,))
    from ...tools.shell import run_shell

    # Ezilen/silinen dosyalar SON turun `/undo` kaydına EKLENİR (ayrı küme açılıp önceki
    # ajan turunun kaydı ezilmez): `/undo` hem ajanın düzenlemesini hem kabuğunkini geri alır.
    changes = state.last_changes if state.last_changes is not None else ChangeSet()
    context = ToolContext(
        root=state.root,
        extra_roots=state.extra_roots,
        restrict_to_root=state.config.runtime.restrict_to_root,
        changes=changes,
    )
    # Komut senkron çalışır (zaman aşımı aracın kendi sınırı); olay döngüsü bloklanmaz.
    result = await asyncio.to_thread(run_shell, {"command": command}, context)
    if changes:
        state.last_changes = changes
    output = (
        result.output
        if len(result.output) <= MAX_OUTPUT_CHARS
        else result.output[:MAX_OUTPUT_CHARS]
    )
    # Bağlama giden kopya maskeli; ekrana basılan çıktı kullanıcının kendi terminalidir.
    block = messages.SHELL_PREFIX_BLOCK.format(
        command=redact(command), status="tamam" if result.ok else "hata", output=redact(output)
    )
    push_pending_context(state, block)
    return ShellPrefixResult(output, result.ok, context_block=block)


def add_memory_note(state: ReplState, note: str) -> str:
    """`# not` — düz metin belleğin `## Notlar` bölümüne yaz; sonuç satırı döner (P-036)."""
    if state.plain_memory is None:
        return messages.MEMORY_OFF_HINT
    if not note.strip():
        return messages.MEMORY_NOTE_EMPTY
    try:
        written = state.plain_memory.note(note)
    except PlainMemoryError as error:
        return str(error)
    return messages.MEMORY_NOTE_SAVED.format(path=written.path, lines=written.lines)
