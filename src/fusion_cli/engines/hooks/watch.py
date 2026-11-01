"""Oturum boyu dosya izleyicisi: `ConfigChange` ve `FileChanged` kancaları (#90, #121, #126).

Claude Code ayar dosyalarını ve izlenen dosyaları bir dosya sistemi izleyicisiyle izler;
değişikliği kim yaptıysa (araç, kabuk, dışarıdaki süreç) kanca çalışır. Fusion bunu
bağımlılıksız, `stat` yoklamasıyla yapar (`POLL_S` aralığı; kök tur başında da bir kez).

`ConfigChange`: kullanıcı/proje/yerel/yönetilen ayar dosyası ya da `.claude/skills/`
altındaki bir beceri dosyası değişince; eşleştirici `source`'tur. Engellenmeyen değişiklik
kanca tanımlarına HEMEN uygulanır (tur ortasında da). Çıkış 2 ya da `decision: block`
değişikliği çalışan oturuma uygulamaz: tanımlar sonraki izinli değişikliğe dek eskisi
kalır; `policy_settings` engellenemez. Engel ve gerekçe kimseye gösterilmez (Claude gibi).

`FileChanged`: izleme listesi `FileChanged` eşleştiricilerinin `|` ile ayrılmış parçalarıdır
(çalışma klasöründe birebir dosya adı) ve SessionStart/CwdChanged/FileChanged kancalarının
döndürdüğü `watchPaths` (mutlak yollar). Girdi `file_path`, `event` (`change`/`add`/
`unlink`); `systemMessage` etkileşimli oturumda kısa satır olarak gösterilir.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

from ...config.hooks import LAYER_MANAGED, hook_layers, managed_settings_file
from ...config.permission_rules import LAYER_LOCAL, LAYER_PROJECT
from ...core.hooks.events import HookEvent, HookVerdict
from .session import HookSession

LOG = logging.getLogger(__name__)

#: Yoklama aralığı (sn).
POLL_S = 1.0
#: Beceri klasöründe izlenen en çok dosya (büyük klasörde yoklama pahalılaşmasın).
MAX_SKILL_FILES = 500
SOURCE_USER = "user_settings"
SOURCE_PROJECT = "project_settings"
SOURCE_LOCAL = "local_settings"
SOURCE_POLICY = "policy_settings"
SOURCE_SKILLS = "skills"
_LAYER_SOURCE = {
    LAYER_PROJECT: SOURCE_PROJECT,
    LAYER_LOCAL: SOURCE_LOCAL,
    LAYER_MANAGED: SOURCE_POLICY,
}
EVENT_CHANGE = "change"
EVENT_ADD = "add"
EVENT_UNLINK = "unlink"

#: (mtime_ns, boyut); dosya yoksa `None`.
Stamp = tuple[int, int] | None


def _stamp(path: Path) -> Stamp:
    try:
        info = path.stat()
    except OSError:
        return None
    return (info.st_mtime_ns, info.st_size)


def _file_event(before: Stamp, after: Stamp) -> str | None:
    if before == after:
        return None
    if before is None:
        return EVENT_ADD
    return EVENT_UNLINK if after is None else EVENT_CHANGE


@dataclass(slots=True)
class HookWatcher:
    """Ayar ve izlenen dosyaların son görülen damgaları; `check` farkları kancalara verir."""

    session: HookSession
    _config: dict[Path, Stamp] = field(default_factory=dict)
    _files: dict[Path, Stamp] = field(default_factory=dict)
    task: asyncio.Task[None] | None = None

    def config_sources(self) -> dict[Path, str]:
        """İzlenen ayar dosyaları → `ConfigChange` kaynağı."""
        found = {
            layer.path: _LAYER_SOURCE.get(layer.name, SOURCE_USER)
            for layer in hook_layers(self.session.root, self.session.home)
        }
        managed_dir = managed_settings_file().parent / "managed-settings.d"
        for path in _files_under(managed_dir, MAX_SKILL_FILES):
            found[path] = SOURCE_POLICY
        if self.session.has(HookEvent.CONFIG_CHANGE):
            for path in self._skill_files():
                found[path] = SOURCE_SKILLS
        return found

    def _skill_files(self) -> list[Path]:
        home = self.session.home if self.session.home is not None else Path.home()
        roots = (self.session.root / ".claude" / "skills", home / ".claude" / "skills")
        return [path for root in roots for path in _files_under(root, MAX_SKILL_FILES)]

    def watched_files(self) -> tuple[Path, ...]:
        """`FileChanged` izleme listesi: eşleştirici parçaları + dinamik `watchPaths`."""
        names: dict[Path, None] = {}
        for command in self.session.current().commands:
            if command.event is not HookEvent.FILE_CHANGED:
                continue
            for part in command.matcher.split("|"):
                if part.strip():
                    names[self.session.root / part.strip()] = None
        for text in self.session.watch_paths:
            names[Path(text)] = None
        return tuple(names)

    def prime(self) -> None:
        """Taban damgaları (açılıştan önceki değişiklikler kanca çalıştırmaz)."""
        self._config = {path: _stamp(path) for path in self.config_sources()}
        self._files = {path: _stamp(path) for path in self.watched_files()}

    def config_changes(self) -> list[tuple[Path, str]]:
        sources = self.config_sources()
        changed: list[tuple[Path, str]] = []
        current: dict[Path, Stamp] = {}
        for path, source in sources.items():
            current[path] = _stamp(path)
            if path in self._config and self._config[path] != current[path]:
                changed.append((path, source))
        self._config = current
        return changed

    def file_changes(self) -> list[tuple[Path, str]]:
        changed: list[tuple[Path, str]] = []
        current: dict[Path, Stamp] = {}
        for path in self.watched_files():
            current[path] = _stamp(path)
            kind = _file_event(self._files[path], current[path]) if path in self._files else None
            if kind is not None:
                changed.append((path, kind))
        self._files = current
        return changed

    async def check(self) -> HookVerdict:
        """Değişiklikleri kancalara ver; `FileChanged` kararlarının birleşimi döner."""
        for path, source in self.config_changes():
            await config_changed(self.session, path, source)
        verdicts = [
            await self.session.emit(
                HookEvent.FILE_CHANGED,
                subjects=(path.name,),
                fields={"file_path": str(path), "event": kind},
            )
            for path, kind in self.file_changes()
        ]
        for verdict in verdicts:
            self._show(verdict)
        return verdicts[-1] if verdicts else HookVerdict()

    def _show(self, verdict: HookVerdict) -> None:
        sink = self.session.status_sink
        if not self.session.interactive or sink is None:
            return
        for text in verdict.system_messages:
            sink(text)


async def config_changed(session: HookSession, path: Path, source: str) -> bool:
    """`ConfigChange`: değişiklik uygulandıysa `True` (engel yalnız tanımları sabitler)."""
    verdict = await session.emit(
        HookEvent.CONFIG_CHANGE,
        subjects=(source,),
        fields={"source": source, "file_path": str(path)},
    )
    if verdict.blocked and source != SOURCE_POLICY:
        LOG.debug("ConfigChange %s engellendi: %s", path, verdict.reason)
        session.hooks_pinned = True
        return False
    session.hooks_pinned = False
    session.refresh()
    return True


def _files_under(root: Path, limit: int) -> list[Path]:
    if not root.is_dir():
        return []
    found: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            found.append(path)
            if len(found) >= limit:
                break
    return found


def watcher_of(session: HookSession) -> HookWatcher | None:
    watcher = session.watcher
    return watcher if isinstance(watcher, HookWatcher) else None


def ensure_watcher(session: HookSession, poll_s: float = POLL_S) -> HookWatcher:
    """Oturumun izleyicisini kur ve (çalışan döngü varsa) arka plan yoklamasını başlat."""
    watcher = watcher_of(session)
    if watcher is None:
        watcher = HookWatcher(session)
        watcher.prime()
        session.watcher = watcher
    if watcher.task is None or watcher.task.done():
        with contextlib.suppress(RuntimeError):
            watcher.task = asyncio.get_running_loop().create_task(_poll(watcher, poll_s))
    return watcher


async def check_changes(session: HookSession) -> None:
    """Kök tur başı: bekleyen değişiklikler `refresh`'ten önce kancalara verilir."""
    watcher = watcher_of(session)
    if watcher is not None:
        await watcher.check()


async def _poll(watcher: HookWatcher, poll_s: float) -> None:
    while not watcher.session.ended:
        await asyncio.sleep(poll_s)
        try:
            await watcher.check()
        except (OSError, ValueError) as exc:
            LOG.warning("Kanca dosya izleyicisi: %s", exc)
