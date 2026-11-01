"""`/loop` komutu (P-038): oturum boyunca yineleyen görev.

    /loop 5m <görev|/komut>   sabit aralıkla
    /loop <görev> every 2h    sondaki ifadeyle de aralık verilir (Claude; #345)
    /loop <görev|/komut>      kendi tempolu: hemen çalışır, sıradakini ajan seçer (1 dk–1 sa;
                              seçmezse ~20 dk sonra tek yedek uyanma, sonra biter)
    /loop                     bakım görevi (kendi tempolu): .claude/loop.md, yoksa yerleşik metin
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

import os
import time
from pathlib import Path

from ...core.session_cron import (
    MIN_INTERVAL_S,
    CronTask,
    Kind,
    SessionCronError,
)
from ...ui import messages
from .loop_interval import split_loop_interval
from .state import ReplState

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
        # Kök değişimi, mikrofon ve uzaktan erişim yalnız kullanıcının elinden (P-072).
        "cd",
        "voice",
        "rc",
    }
)
#: Claude'daki yerleşik bakım istemi sırası (#346): yarım işi sürdür → dalın PR'ı → temizlik.
DEFAULT_MAINTENANCE_PROMPT = (
    "Bakım turu. Şu sırayla ilerle: (1) Bu sohbette yarım kalan bir iş varsa onu sürdür. "
    "(2) Yoksa bu dalın PR'ına bak: yorumlar, CI sonuçları, birleştirme çakışmaları; "
    "gerekeni ele al. (3) Başka iş yoksa küçük bir temizlik turu yap. Yeni bir girişim "
    "başlatma; geri alınamaz bir işlemi yalnız bu sohbette daha önce onaylandıysa yap."
)
#: Görevde saklanan yer tutucu: `loop.md` her çalışmada yeniden okunur (#346).
LOOP_MD_PROMPT = "<fusion-loop-md>"
#: `loop.md`'nin okunan en çok bayt sayısı (Claude: 25.000).
LOOP_MD_MAX_BYTES = 25_000


def maintenance_prompt(root: Path, home: Path) -> str:
    """`.claude/loop.md` (proje) → `~/.claude/loop.md` (ev) → yerleşik metin.

    Dosya 25.000 baytta kesilir (Claude).
    """
    for base in (root, home):
        for relative in LOOP_FILES:
            path = base / relative
            try:
                raw = path.read_bytes()[:LOOP_MD_MAX_BYTES]
            except OSError:
                continue
            text = raw.decode("utf-8", errors="ignore").strip()
            if text:
                return text
    return DEFAULT_MAINTENANCE_PROMPT


def command(state: ReplState, argument: str) -> str:
    if os.environ.get("CLAUDE_CODE_DISABLE_CRON", "").strip().lower() in {"1", "true", "yes"}:
        return messages.LOOP_DISABLED
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
    try:
        parsed = split_loop_interval(sub)
    except SessionCronError as error:
        return f"{error} {messages.LOOP_USAGE}"
    prompt = parsed.prompt or LOOP_MD_PROMPT
    blocked = blocked_command(prompt)
    if blocked is not None:
        return messages.LOOP_COMMAND_BLOCKED.format(name=blocked)
    # Claude: aralık verilmezse (görev beceri olsa da) tempoyu ajan seçer (#344).
    every = f"{parsed.minutes}m" if parsed.minutes is not None else None
    try:
        if every is None:
            task = state.cron.create_self_paced(prompt, now=now)
        else:
            task = state.cron.create_interval(prompt, every, now=now)
    except SessionCronError as error:
        return f"{error} {messages.LOOP_USAGE}"
    shown = _shown_prompt(prompt)
    if every is None:
        return messages.LOOP_SET_SELF_PACED.format(id=task.id, prompt=shown)
    text = messages.LOOP_SET.format(id=task.id, every=every, prompt=shown, min=MIN_INTERVAL_S // 60)
    if parsed.rounded_from:
        text += "\n" + messages.LOOP_ROUNDED.format(raw=parsed.rounded_from, every=every)
    return text


def _shown_prompt(prompt: str) -> str:
    return messages.LOOP_MD_LABEL if prompt == LOOP_MD_PROMPT else prompt[:80]


def fire_prompt(task: CronTask, *, root: Path | None = None, home: Path | None = None) -> str:
    """Vadesi gelen görevin tura giden metni; kendi tempolu döngüye tempo talimatı eklenir.

    Argümansız `/loop` görevi `loop.md`'yi HER çalışmada yeniden okur (Claude; #346).
    """
    prompt = task.prompt
    if prompt == LOOP_MD_PROMPT:
        prompt = maintenance_prompt(root or Path.cwd(), home or Path.home())
    if task.kind is not Kind.SELF_PACED:
        return prompt
    return messages.LOOP_SELF_PACED_TASK.format(prompt=prompt, id=task.id)


def _is_slash(prompt: str) -> bool:
    from .commands import is_command_line

    return is_command_line(prompt)


def blocked_command(prompt: str) -> str | None:
    """Görev metni yasaklı bir slash komutuysa adını döndür; değilse None.

    Takma ad kanonik ada çevrilir. Ölçüldü (31 Ekim): ham ada bakıldığı için `/dikte`
    (voice), `/q`, `/dev`, `/manuel` yasağı aşıyordu.
    """
    # `commands` bu modülü içe aktarır; döngüyü kırmak için burada yüklenir.
    from .commands import build_registry, is_command_line, parse

    if not is_command_line(prompt):
        return None
    name, _argument = parse(prompt)
    command = build_registry().get(name)
    canonical = command.name if command is not None else name
    return name if canonical in BLOCKED_COMMANDS else None
