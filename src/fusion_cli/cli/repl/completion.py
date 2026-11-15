"""Birleşik tamamlayıcı (P-022): `/` komut adları, `@` yol tamamlama.

Eskiden yalnız `WordCompleter` komut adlarını tamamlıyordu. Burada imlecin önündeki
sözcüğe bakılır:

- `/` ile başlıyor ve satırın ilk sözcüğüyse → komut adları (eski davranış).
- `@` ile başlıyorsa → proje kökünde (ve ek köklerde) yol tamamlama; dizin parçası
  yazıldıkça o dizinin içinde gezilir, dosya adında ALT DİZİ (fuzzy) eşleşmesi yeter.
  `.git`, `node_modules` gibi gürültü dizinleri ve gizli dosyalar (nokta ile başlayan),
  kullanıcı noktayı yazmadıkça listelenmez.

Satır-içi `PromptSession` ve tam-ekran `TextArea` aynı sınıfı kullanır.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from pathlib import Path

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document

from . import emoji_codes

#: Yol tamamlamada hiç listelenmeyen dizinler.
NOISE_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache"})
#: Bir seferde gösterilecek en fazla öneri.
MAX_SUGGESTIONS = 30


def fuzzy_match(candidate: str, typed: str) -> bool:
    """`typed` harfleri `candidate` içinde SIRAYLA geçiyor mu (büyük/küçük duyarsız)?"""
    if not typed:
        return True
    haystack = candidate.casefold()
    position = 0
    for char in typed.casefold():
        position = haystack.find(char, position)
        if position < 0:
            return False
        position += 1
    return True


def path_suggestions(partial: str, roots: Iterable[Path]) -> list[str]:
    """`@` sonrası yazılan parça için aday yollar (köke göreli, dizinler `/` ile biter)."""
    directory_part, _, name_part = partial.rpartition("/")
    seen: list[str] = []
    for root in roots:
        base = root / directory_part if directory_part else root
        try:
            entries = sorted(base.iterdir(), key=lambda entry: (not entry.is_dir(), entry.name))
        except OSError:
            continue
        for entry in entries:
            name = entry.name
            if name in NOISE_DIRS:
                continue
            if name.startswith(".") and not name_part.startswith("."):
                continue
            if not fuzzy_match(name, name_part):
                continue
            suggestion = f"{directory_part}/{name}" if directory_part else name
            if entry.is_dir():
                suggestion += "/"
            if suggestion not in seen:
                seen.append(suggestion)
            if len(seen) >= MAX_SUGGESTIONS:
                return seen
    return seen


def agent_suggestions(partial: str, agents: Iterable[str]) -> list[str]:
    """`@` sonrası parçaya uyan ajanlar `agent-<ad>` biçiminde (`@agent-co`, `@revi`)."""
    typed = partial.casefold()
    return [
        f"agent-{name}"
        for name in agents
        if f"agent-{name}".casefold().startswith(typed) or typed in name.casefold()
    ][:MAX_SUGGESTIONS]


def _mcp_resource_mentions() -> list[tuple[str, str]]:
    from .mcp_prompt_commands import resource_mentions

    return resource_mentions()


def agent_names(state: object) -> list[str]:
    """Oturumun etkin ajan adları (katalog yoksa boş); tamamlama hatası istemi bozmaz."""
    library = getattr(state, "capabilities", None)
    if library is None:
        return []
    return [item.name for item in library.agents()]


def live_session_names(state: object) -> list[str]:
    """`@` önerisi için canlı öteki oturumlar (Claude Code typeahead, #228); kendisi hariç."""
    link = getattr(state, "agent_link", None)
    if link is None:
        return []
    own = getattr(getattr(link, "peer", None), "id", None)
    try:
        peers = link.registry.peers()
    except OSError:
        return []
    return [peer.name or peer.id for peer in peers if peer.id != own]


class ReplCompleter(Completer):
    """Komut adı ve `@yol` tamamlayıcısı."""

    def __init__(
        self,
        words: list[str] | Callable[[], list[str]],
        roots: tuple[Path, ...] | Callable[[], tuple[Path, ...]],
        *,
        agents: Callable[[], list[str]] | None = None,
        shell_history: Callable[[], Iterable[str]] | None = None,
        mcp_resources: Callable[[], Iterable[tuple[str, str]]] | None = None,
        sessions: Callable[[], list[str]] | None = None,
    ) -> None:
        #: Çağrılabilirse her tamamlamada yeniden alınır (dinamik beceri komutları, P-019).
        self._words = words
        #: Kökler de çağrılabilir olabilir: `/cd`, `/add-dir`, `/worktree` sonrası `@yol`
        #: tamamlaması yeni köke bakar (P-072; ölçüldü 31 Ekim: açılış köküne çiviliydi).
        self._roots = roots
        #: Etkin alt ajan adları: `@agent-<ad>` önerisi (Claude Code typeahead, #26).
        self._agents = agents
        #: `!` kabuk kipinde Tab geçmişteki `!` satırlarını önerir (Claude Code, #219).
        self._shell_history = shell_history
        #: `@sunucu:uri` MCP kaynakları dosyalarla birlikte önerilir (Claude Code, #228, #254);
        #: verilmezse bağlı sunucuların kataloğu okunur.
        self._mcp_resources = mcp_resources or _mcp_resource_mentions
        #: Canlı öteki oturumlar: `@ad mesaj` o oturuma gönderilir (#228).
        self._sessions = sessions

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterator[Completion]:
        word = document.get_word_before_cursor(WORD=True)
        typed = document.text_before_cursor.lstrip()
        if typed.startswith("!"):
            yield from self._shell_completions(typed, word)
            return
        if word.startswith("@"):
            partial = word[1:]
            for name in agent_suggestions(partial, self._agents() if self._agents else []):
                yield Completion(f"@{name}", start_position=-len(word), display=name)
            for name in self._sessions() if self._sessions else []:
                if fuzzy_match(name, partial):
                    yield Completion(
                        f"@{name}", start_position=-len(word), display=name, display_meta="oturum"
                    )
            roots = self._roots() if callable(self._roots) else self._roots
            for suggestion in path_suggestions(partial, roots):
                yield Completion(f"@{suggestion}", start_position=-len(word), display=suggestion)
            for mention, name in self._mcp_resources():
                if fuzzy_match(mention, partial) or fuzzy_match(name, partial):
                    yield Completion(
                        f"@{mention}", start_position=-len(word), display=mention, display_meta=name
                    )
            return
        emoji_prefix = emoji_codes.shortcode_prefix(word) if word.startswith(":") else None
        if emoji_prefix is not None:
            # `:emoji:` kısa kodları (#216): seçilen öneri sözcüğü emojiyle değiştirir.
            for name, emoji in emoji_codes.suggestions(emoji_prefix):
                yield Completion(emoji, start_position=-len(word), display=f"{emoji} :{name}:")
            return
        if word.startswith("/") and document.text_before_cursor.lstrip() == word:
            words = self._words() if callable(self._words) else self._words
            for candidate in words:
                if candidate.startswith(word):
                    yield Completion(candidate, start_position=-len(word))

    def _shell_completions(self, typed: str, word: str) -> Iterator[Completion]:
        """`!` kipi (#219): önce geçmişteki `!` komutları, sonra son sözcük için yollar."""
        seen: set[str] = set()
        for line in self._shell_history() if self._shell_history else ():
            entry = line.strip()
            matches = entry.startswith("!") and entry != typed and entry.startswith(typed)
            if matches and entry not in seen and len(seen) < MAX_SUGGESTIONS:
                seen.add(entry)
                yield Completion(entry, start_position=-len(typed), display=entry)
        if word.startswith("!") or (not word and typed == "!"):
            return
        roots = self._roots() if callable(self._roots) else self._roots
        for suggestion in path_suggestions(word, roots):
            yield Completion(suggestion, start_position=-len(word), display=suggestion)
