"""Option+P / Option+T / Option+O (#216, Claude Code `chat:modelPicker`,
`chat:thinkingToggle`, `chat:fastMode`).

Terminal "Option as Meta" ayarlıysa Option+harf `ESC` + harf olarak gelir. Tam ekran TUI'de
Esc anında (eager) bağlı kesme tuşudur; bu yüzden `escape p` dizisi prompt_toolkit'te hiç
eşleşmez. Çözüm: Meta dizisi terminalden TEK okumada gelir, insan eliyle basılan Esc ve
ardından gelen harf ayrı okumalarda gelir. Esc işleyicisi çalışırken aynı okumanın kalan
tuşları `key_processor.input_queue`'dadır; sıradaki tuş tek harfse ve tabloda `escape <harf>`
bağı varsa harf kuyruktan alınır ve kesme yerine o eylem çalışır.

Satır içi istemde Esc eager değildir; `escape p` bağları doğrudan çalışır.
"""

from __future__ import annotations

from collections.abc import Mapping

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
