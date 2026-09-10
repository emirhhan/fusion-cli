"""Bir Fusion web profilini süreçler arasında paylaşan tek Chrome.

Masaüstünde her sekme ayrı bir `fusion app` sürecidir. Eskiden her süreç aynı
izole profil için KENDİ Playwright Chrome'unu açıyordu; Chrome bir profili yalnız
bir sürece verdiği için ikinci sekme "Bu Fusion Chrome profili hâlâ açık" hatasıyla
düşüyordu (ölçüldü: 7 sekme süreci, tek `gemini_web/main` profili).

Artık profil başına tek bir Chrome çalışır ve yalnız loopback üzerinde hata
ayıklama portu açar. Her süreç ona CDP ile bağlanır ve kendi sayfalarını kullanır.
Chrome'u hangi süreçlerin kullandığı profil dizinindeki kira dosyalarında tutulur;
son kiracı çıkınca Chrome kapatılır, çöken süreçlerin kiraları budanır.

Bu modül Playwright tanımaz: başlatma, kapatma ve uç nokta yoklaması
`SharedBrowserHooks` ile verilir. Böylece süreçler arası kilit ve kira mantığı
gerçek tarayıcı açılmadan test edilir.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

if sys.platform != "win32":
    import fcntl
else:  # pragma: no cover - Windows'ta kilit dosyası yedeği kullanılır
    fcntl = None

#: Chrome'un profil dizinine yazdığı hata ayıklama portu dosyası.
DEVTOOLS_PORT_FILE = "DevToolsActivePort"
LOCK_FILE = ".fusion-browser.lock"
LEASE_DIR = ".fusion-leases"
#: Kilit ve port dosyası yoklama aralığı. Yalnız bekleme sıklığıdır; toplam
#: bekleme süresini çağıranın tarayıcı tur bütçesi belirler.
POLL_INTERVAL_S = 0.1


class SharedBrowserError(RuntimeError):
    """Paylaşılan tarayıcı başlatılamadı ya da profil kilitlenemedi."""


@dataclass(frozen=True, slots=True)
class SharedBrowserHooks:
    """Paylaşılan tarayıcının dış dünyaya dokunan işlemleri."""

    #: Profili bu süreç açmadan önce hazırla; profil başka bir Chrome'daysa hata ver.
    prepare_launch: Callable[[Path], None]
    #: Profille hata ayıklama portu açık Chrome başlat (beklemeden döner).
    launch: Callable[[Path, bool], Awaitable[None]]
    #: Uç nokta gerçekten yanıt veriyor mu?
    is_alive: Callable[[str], Awaitable[bool]]
    #: Uç noktadaki Chrome'u düzgünce kapat.
    close: Callable[[str], Awaitable[None]]


def read_endpoint(profile: Path) -> str | None:
    """Chrome'un yazdığı port dosyasından CDP adresini oku."""
    try:
        first_line = (profile / DEVTOOLS_PORT_FILE).read_text(encoding="utf-8").splitlines()[0]
        port = int(first_line.strip())
    except (OSError, IndexError, ValueError):
        return None
    return f"http://127.0.0.1:{port}" if port > 0 else None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


class SharedProfileBrowser:
    """Tek bir profilin paylaşılan Chrome'unu kiralayan ve bırakan nesne."""

    def __init__(self, profile: Path, hooks: SharedBrowserHooks, *, owner_pid: int) -> None:
        self._profile = profile
        self._hooks = hooks
        self._owner_pid = owner_pid

    async def acquire(self, *, headless: bool, timeout_s: float) -> str:
        """Çalışan Chrome'u kirala; yoksa başlat. CDP adresini döndür.

        Profil başka bir modda açıksa (ör. görünür) o Chrome kullanılır: tek
        profil aynı anda iki Chrome'a verilemez.
        """
        deadline = time.monotonic() + timeout_s
        self._profile.mkdir(parents=True, exist_ok=True)
        async with self._locked(deadline):
            endpoint = await self._running_endpoint()
            if endpoint is None:
                endpoint = await self._launch(headless=headless, deadline=deadline)
            leases = self._profile / LEASE_DIR
            leases.mkdir(exist_ok=True)
            (leases / str(self._owner_pid)).touch()
            return endpoint

    async def release(self, *, force: bool, timeout_s: float) -> None:
        """Kirayı bırak; son kiracıysa ya da `force` verildiyse Chrome'u kapat.

        `force` giriş penceresi içindir: kullanıcı profili elle açacağı için diğer
        süreçlerin kiraları beklenmez, onlar sonraki turda yeniden bağlanır.
        """
        if not self._profile.is_dir():
            return
        async with self._locked(time.monotonic() + timeout_s):
            with contextlib.suppress(FileNotFoundError):
                (self._profile / LEASE_DIR / str(self._owner_pid)).unlink()
            if not force and self._live_leases():
                return
            endpoint = read_endpoint(self._profile)
            if endpoint is not None and await self._hooks.is_alive(endpoint):
                await self._hooks.close(endpoint)
            self._clear_leases()

    async def _running_endpoint(self) -> str | None:
        endpoint = read_endpoint(self._profile)
        if endpoint is not None and await self._hooks.is_alive(endpoint):
            return endpoint
        return None

    async def _launch(self, *, headless: bool, deadline: float) -> str:
        # Canlı Chrome yoksa eski kiralar da geçersizdir: sahipleri artık yok.
        self._clear_leases()
        self._hooks.prepare_launch(self._profile)
        with contextlib.suppress(FileNotFoundError):
            (self._profile / DEVTOOLS_PORT_FILE).unlink()
        await self._hooks.launch(self._profile, headless)
        while time.monotonic() < deadline:
            endpoint = await self._running_endpoint()
            if endpoint is not None:
                return endpoint
            await asyncio.sleep(POLL_INTERVAL_S)
        raise SharedBrowserError(
            "Fusion Chrome'u zamanında açılmadı. Chrome kurulu mu kontrol edip tekrar dene."
        )

    def _live_leases(self) -> list[int]:
        """Yaşayan kiracıları döndür; çökmüş süreçlerin kiralarını sil."""
        live: list[int] = []
        directory = self._profile / LEASE_DIR
        if not directory.is_dir():
            return live
        for lease in directory.iterdir():
            try:
                pid = int(lease.name)
            except ValueError:
                continue
            if _pid_alive(pid):
                live.append(pid)
            else:
                with contextlib.suppress(FileNotFoundError):
                    lease.unlink()
        return live

    def _clear_leases(self) -> None:
        directory = self._profile / LEASE_DIR
        if directory.is_dir():
            for lease in directory.iterdir():
                with contextlib.suppress(FileNotFoundError):
                    lease.unlink()

    @contextlib.asynccontextmanager
    async def _locked(self, deadline: float) -> AsyncIterator[None]:
        """Profil kilidini süreçler arası al; event loop'u bloklamadan bekle."""
        path = self._profile / LOCK_FILE
        if sys.platform == "win32":  # pragma: no cover - POSIX dışı
            async with _exclusive_file_lock(path.with_suffix(".fallback"), deadline):
                yield
            return
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise SharedBrowserError(_LOCK_TIMEOUT_MESSAGE) from None
                    await asyncio.sleep(POLL_INTERVAL_S)
            try:
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


_LOCK_TIMEOUT_MESSAGE = (
    "Başka bir Fusion sekmesi tarayıcıyı hazırlıyor ve zamanında bitirmedi. Tekrar dene."
)


@contextlib.asynccontextmanager
async def _exclusive_file_lock(path: Path, deadline: float) -> AsyncIterator[None]:
    """`flock` olmayan sistemde atomik kilit dosyası."""
    while True:
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise SharedBrowserError(_LOCK_TIMEOUT_MESSAGE) from None
            await asyncio.sleep(POLL_INTERVAL_S)
    try:
        yield
    finally:
        os.close(descriptor)
        _remove_file(path)


def _remove_file(path: Path) -> None:
    """Kilit dosyasını sil; async gövdede dosya sistemi yöntemi çağrılmasın diye ayrı."""
    path.unlink(missing_ok=True)


#: Loopback uç noktasına tek yoklamanın süresi. Canlı Chrome yerel isteğe anında
#: yanıt verir; toplam bekleme yine çağıranın tur bütçesiyle sınırlıdır.
ENDPOINT_PROBE_TIMEOUT_S = 1.0


async def endpoint_alive(endpoint: str) -> bool:
    """Port dosyası geride kalmış ölü bir Chrome'u canlı sanma."""
    try:
        async with httpx.AsyncClient(timeout=ENDPOINT_PROBE_TIMEOUT_S) as client:
            response = await client.get(f"{endpoint}/json/version")
    except httpx.HTTPError:
        return False
    return response.status_code == 200


def chrome_launch_arguments(executable: str, profile: Path, *, headless: bool) -> list[str]:
    """Paylaşılan Chrome'un komut satırı.

    Port 0: işletim sistemi boş port seçer, Chrome onu `DevToolsActivePort`'a
    yazar. Chrome hata ayıklama portunu yalnız loopback'e bağlar. Otomasyon
    bayrağı yoktur; işletim sistemi anahtarlığı normal Chrome'daki gibi kullanılır.
    """
    arguments = [
        executable,
        f"--user-data-dir={profile}",
        "--remote-debugging-port=0",
        "--no-first-run",
        "--no-default-browser-check",
        "--lang=tr-TR",
        "--window-size=1440,1000",
    ]
    if headless:
        arguments.append("--headless=new")
    arguments.append("about:blank")
    return arguments
