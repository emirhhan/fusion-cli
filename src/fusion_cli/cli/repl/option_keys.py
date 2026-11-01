"""Option+P / Option+T / Option+O (#216, Claude Code `chat:modelPicker`,
`chat:thinkingToggle`, `chat:fastMode`).

Terminal "Option as Meta" ayarlıysa Option+harf `ESC` + harf olarak gelir. Tam ekran TUI'de
Esc anında (eager) bağlı kesme tuşudur; bu yüzden `escape p` dizisi prompt_toolkit'te hiç
eşleşmez. Çözüm: Meta dizisi terminalden TEK okumada gelir, insan eliyle basılan Esc ve
ardından gelen harf ayrı okumalarda gelir. Esc işleyicisi çalışırken aynı okumanın kalan
tuşları `key_processor.input_queue`'dadır; sıradaki tuş tek harfse ve tabloda `escape <harf>`
bağı varsa harf kuyruktan alınır ve kesme yerine o eylem çalışır.

Satır içi istemde Esc eager değildir; emacs kipinde `escape p` bağları doğrudan çalışır. Vim
kipinde ise Esc NORMAL'e geçiştir: `escape <harf>` bağı açık kalırsa elle basılan Esc'ten hemen
sonra gelen `o`/`p`/`t` vim komutu yerine Option eylemi olur. Bu yüzden vim kipinde `escape …`
bağları kapanır (`vim_filter`), Option+harf TUI'deki tek okuma sezgisiyle tanınır
(`add_vi_meta_binding`), tek karakterli bağlar (`?`) NORMAL kipte vim'e bırakılır.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

#: Varsayılan Meta bağları (her iki bağlam).
DEFAULTS: dict[str, str] = {
    "escape p": "model_sec",
    "escape t": "dusunme",
    "escape o": "hizli_kip",
}
#: Fusion'da hızlı kip yoktur (Claude Code `/fast`: Anthropic sunucusundaki hızlı çıktı).
FAST_UNAVAILABLE = (
    "Option+O: hızlı kip (Claude Code /fast) Anthropic sunucusundaki hızlı çıktı modudur; "
    "Fusion'da yok. Daha hızlı yanıt için /model ile hızlı bir model seçin."
)


def take_meta_action(app: object, bindings: Mapping[str, str]) -> str | None:
    """Esc ile aynı okumada gelen harfin `escape <harf>` eylemi; yoksa None (kuyruk aynen)."""
    queue = getattr(getattr(app, "key_processor", None), "input_queue", None)
    if not queue:
        return None
    key = getattr(queue[0], "key", None)
    if not isinstance(key, str) or len(key) != 1:
        return None
    action = bindings.get(f"escape {key.lower()}")
    if action is None:
        return None
    queue.popleft()
    return action


def _queued_meta_action(app: object, bindings: Mapping[str, str]) -> str | None:
    """Kuyruğu değiştirmeden: Esc ile aynı okumada gelen harfin eylemi."""
    queue = getattr(getattr(app, "key_processor", None), "input_queue", None)
    key = getattr(queue[0], "key", None) if queue else None
    if not isinstance(key, str) or len(key) != 1:
        return None
    return bindings.get(f"escape {key.lower()}")


def vim_filter(key: str) -> Any:
    """Satır içi bağın vim kipiyle çakışmayan süzgeci; çakışma yoksa None."""
    from prompt_toolkit.filters import vi_mode, vi_navigation_mode, vi_selection_mode

    if key == "escape" or key.startswith("escape "):
        return ~vi_mode
    if len(key) == 1:
        return ~(vi_navigation_mode | vi_selection_mode)
    return None


def add_vi_meta_binding(
    bindings: Any, table: Mapping[str, str], resolve: Callable[[str], Callable[[Any], None] | None]
) -> None:
    """Vim kipinde Option+harf: Esc işlenirken harf aynı okumadan kuyruktaysa o eylem çalışır."""
    from prompt_toolkit.application import get_app
    from prompt_toolkit.filters import Condition, vi_mode

    meta = {key: action for key, action in table.items() if key.startswith("escape ")}
    if not meta:
        return

    @Condition
    def _meta_in_same_read() -> bool:
        return _queued_meta_action(get_app(), meta) is not None

    @bindings.add("escape", filter=vi_mode & _meta_in_same_read)
    def _option(event: Any) -> None:
        action = take_meta_action(event.app, meta)
        handler = resolve(action) if action is not None else None
        if handler is not None:
            handler(event)
