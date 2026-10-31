"""`/loop` komutu (P-038): oturum boyunca yineleyen görev.

    /loop 5m <görev|/komut>   sabit aralıkla
    /loop <görev>             varsayılan aralıkla (10 dk)
    /loop                     bakım görevi: .claude/loop.md (proje ya da ev), yoksa yerleşik metin
    /loop list                görevleri listele
    /loop stop [id|all]       görevi (ya da hepsini) durdur

Görev `ReplState.cron`'a yazılır; vadesi gelince REPL boştayken yeni tur olarak
gönderilir (`loop._cron_watcher`, `tui_loop._TuiSession._cron_watcher`). Slash
komutu da görev olabilir (`/loop 30m /verify`): satır komut olarak işlenir — yalnız
KULLANICININ kurduğu görevde; ajanın `cron_create` ile kurduğu görev her zaman tur
olur. Onay kipini/modeli/oturumu değiştiren komutlar (`/bypass`, `/auto`, `/mode`…)
zamanlanamaz: `BLOCKED_COMMANDS`.
"""

from __future__ import annotations

import time
from pathlib import Path

from ...core.session_cron import MIN_INTERVAL_S, SessionCronError, looks_like_interval
from ...ui import messages
from .state import ReplState

#: Aralık verilmeyen `/loop <görev>` için varsayılan (Claude Code'un kendi-tempolu döngüsü
#: 1 dk-1 sa arasında salınır; sabit 10 dk güvenli orta nokta).
DEFAULT_INTERVAL = "10m"
#: Argümansız `/loop`'un okuduğu bakım dosyaları (proje, sonra ev).
LOOP_FILES = (Path(".claude") / "loop.md",)
#: Zamanlanmış satır olarak REDDEDİLEN komutlar: onay kipi, model/sağlayıcı ve oturum
#: durumu yalnız kullanıcının elinden değişir; `/loop` kendini zamanlayamaz.
BLOCKED_COMMANDS = frozenset(
    {
        "auto",
        "edits",
        "security",
        "plan",
        "bypass",
        "mode",
        "level",
        "provider",
        "development",
        "model",
        "loop",
        "exit",
        "quit",
        "clear",
    }
)
DEFAULT_MAINTENANCE_PROMPT = (
    "Bakım turu: çalışma ağacındaki değişiklikleri gözden geçir, testleri ve lint'i koştur, "
    "kırık bir şey varsa düzelt; her şey yeşilse kısa bir durum özeti ver ve dur."
)


def maintenance_prompt(root: Path, home: Path) -> str:
    """`.claude/loop.md` (proje) → `~/.claude/loop.md` (ev) → yerleşik metin."""
    for base in (root, home):
        for relative in LOOP_FILES:
            path = base / relative
            try:
                text = path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if text:
                return text
    return DEFAULT_MAINTENANCE_PROMPT


def _split(argument: str) -> tuple[str | None, str]:
    """Baştaki aralığı ayır: `5m testleri koştur` → ("5m", "testleri koştur")."""
    parts = argument.strip().split(None, 1)
    if not parts or not looks_like_interval(parts[0]):
        return None, argument.strip()
    return parts[0], parts[1] if len(parts) > 1 else ""


def command(state: ReplState, argument: str) -> str:
    sub = argument.strip()
    now = time.time()
    head = sub.split(None, 1)[0].casefold() if sub else ""
    if head in {"list", "liste"}:
        tasks = state.cron.list(now)
        if not tasks:
            return messages.LOOP_EMPTY
        return "\n".join(
            [messages.LOOP_LIST_TITLE.format(count=len(tasks))]
            + [f"  {task.describe()}" for task in tasks]
        )
    if head in {"stop", "dur", "durdur"}:
        target = sub.split(None, 1)[1].strip() if len(sub.split(None, 1)) > 1 else ""
        if not target or target.casefold() in {"all", "hepsi"}:
            return messages.LOOP_STOPPED_ALL.format(count=state.cron.clear())
        if state.cron.delete(target):
            return messages.LOOP_STOPPED.format(id=target)
        return messages.LOOP_NOT_FOUND.format(id=target)
    interval, prompt = _split(sub)
    if not prompt:
        prompt = maintenance_prompt(state.root, state.home)
    blocked = blocked_command(prompt)
    if blocked is not None:
        return messages.LOOP_COMMAND_BLOCKED.format(name=blocked)
    try:
        task = state.cron.create_interval(prompt, interval or DEFAULT_INTERVAL, now=now)
    except SessionCronError as error:
        return f"{error} {messages.LOOP_USAGE}"
    return messages.LOOP_SET.format(
        id=task.id, every=interval or DEFAULT_INTERVAL, prompt=prompt[:80], min=MIN_INTERVAL_S // 60
    )


def blocked_command(prompt: str) -> str | None:
    """Görev metni yasaklı bir slash komutuysa adını döndür; değilse None."""
    # `commands` bu modülü içe aktarır; döngüyü kırmak için burada yüklenir.
    from .commands import is_command_line, parse

    if not is_command_line(prompt):
        return None
    name, _argument = parse(prompt)
    return name if name in BLOCKED_COMMANDS else None
