"""Masaüstüsüz uzaktan kontrol sunucusu (`fusion remote-control`, REPL `/rc`) (P-039).

Claude Code `claude remote-control` örneğinde olduğu gibi: aynı süreçte uzak HTTP yüzünü
kaldırır, eşleştirme kodunu (ve adresi) terminale verir, telefon/Telegram bu süreçteki
oturumu sürer. İkinci bir ajan motoru değildir; `RemoteController` ve onun arkasındaki
`AppSession` yürütücüsü aynen kullanılır. Bu modül terminal kütüphanesi tanımaz: metin
üretir, basmayı `cli` katmanı yapar.

Ölçüldü (31 Ekim): `app.py`'de remote komutu yoktu; `remote/` yalnız masaüstü `uzak.*`
istekleriyle ayağa kalkıyordu, terminalden eşleştirme kodu alınamıyordu.

Ölçüldü (31 Ekim, bağımsız inceleme): `--telegram` açıkken de tek kod (PWA kanalı) üretiliyordu;
bot `/pair` yalnız Telegram kanalı kodunu kabul ettiği için Telegram kullanıcısı hiç
eşleşemiyordu. Kodlar artık kanal başına tutulur; Telegram kodu hep elle onaylanır.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from ..core.errors import FusionError
from .constants import DEFAULT_REMOTE_PORT
from .controller import RemoteController
from .scopes import DEFAULT_SCOPES, is_elevated, parse_scopes

#: `uzak.eslestir_baslat` isteğindeki kanal adları (denetleyici "telegram" dışını imzalı sayar).
CHANNEL_REQUEST_PWA = "pwa"
CHANNEL_REQUEST_TELEGRAM = "telegram"


class RemoteControlError(FusionError):
    """Uzaktan kontrol sunucusu kurulamadı; mesaj kullanıcıya gösterilir."""


@dataclass(frozen=True, slots=True)
class PendingApproval:
    question_id: str
    title: str
    target: str
    is_approval: bool


@dataclass(frozen=True, slots=True)
class TaskLine:
    run_id: str
    state: str
    summary: str


@dataclass(frozen=True, slots=True)
class PairingCode:
    """Kanal başına geçerli eşleştirme kodu; `expires_at` sonrası kullanılmamışsa düşer."""

    channel: str
    code: str
    expires_at: float


@dataclass(frozen=True, slots=True)
class RemoteControlStart:
    """`start` sonucu: adres, eşleştirme kodu ve uyarılar (sır içermez)."""

    address: str
    code: str
    expires_at: float
    scopes: tuple[str, ...]
    needs_desktop_approval: bool
    telegram: bool
    warnings: tuple[str, ...] = ()
    #: Telegram köprüsü bağlandıysa bota `/pair` ile yazılacak ayrı kod; yoksa boş.
    telegram_code: str = ""


@dataclass(frozen=True, slots=True)
class RemoteControlSnapshot:
    """Durum fotoğrafı; iki fotoğraf arası fark terminale satır olur."""

    listening: bool
    address: str
    device_count: int
    last_paired: str
    last_paired_at: float
    pending: tuple[PendingApproval, ...] = ()
    tasks: tuple[TaskLine, ...] = field(default_factory=tuple)
    awaiting_device: str = ""


#: Terminal satırları: durum farkı anlatımı (ui katmanı dışındaki tek metin kümesi; Rich yok).
TEXT_PAIRED = "{name} bağlandı."
TEXT_AWAITING = "{name} kodu girdi; onay bekliyor (`onayla`)."
TEXT_APPROVAL = "Onay bekliyor: {title}{target} — telefondan ya da Telegram'dan cevapla."
TEXT_QUESTION = "Soru bekliyor: {title} — telefondan cevapla."
TEXT_TASK = "Görev {run_id}: {state} — {summary}"
TEXT_TELEGRAM_MISSING = (
    "Telegram bağlanmadı: kayıtlı bot belirteci yok. Masaüstünde Ayarlar › Uzaktan Erişim'den "
    "bir kez bağla; belirteç anahtarlıkta saklanır."
)
TEXT_ELEVATED_SCOPES = (
    "Yüksek yetkili kapsam seçildi ({scopes}): cihaz kodu girdikten sonra bu terminalde "
    "onaylaman gerekir."
)
TEXT_TRUST_SETTING_OFF = (
    "--onay-saat verildi ama 'cihaz başına süreli yetki iste' ayarı kapalı: bu ayar kapalıyken "
    "her eşleşmiş cihaz onay verebilir, süreli yetki yalnız ayar açılınca anlam kazanır "
    "(masaüstü Ayarlar › Uzaktan Erişim › Uzaktan onay)."
)


class RemoteControlHost:
    """Tek bir sunucu ömrünü yönetir: başlat → kod ver → izle → durdur."""

    def __init__(
        self,
        controller: RemoteController,
        *,
        extra_scopes: Iterable[str] = (),
        approval_hours: float = 0.0,
    ) -> None:
        self._controller = controller
        self._scopes = frozenset(DEFAULT_SCOPES) | frozenset(extra_scopes)
        try:
            parse_scopes(sorted(self._scopes))  # bilinmeyen kapsam burada, dinlemeden önce düşer
        except ValueError as error:
            raise RemoteControlError(str(error)) from error
        self._approval_hours = approval_hours
        #: Kanal → geçerli kod. Sırası: eklenme sırası (PWA ilk).
        self._codes: dict[str, PairingCode] = {}
        #: Kod üretilmesi beklenen kanallar; `renew_codes` eksik olanı tamamlar.
        self._channels: tuple[str, ...] = ()
        self._started = False

    @property
    def code(self) -> str:
        """PWA (imzalı kanal) kodu; eski çağıranlar için tek kod görünümü."""
        return self._code_of(CHANNEL_REQUEST_PWA)

    @property
    def telegram_code(self) -> str:
        return self._code_of(CHANNEL_REQUEST_TELEGRAM)

    @property
    def codes(self) -> tuple[PairingCode, ...]:
        return tuple(self._codes.values())

    @property
    def started(self) -> bool:
        return self._started

    @property
    def telegram_connected(self) -> bool:
        return CHANNEL_REQUEST_TELEGRAM in self._channels

    @property
    def needs_desktop_approval(self) -> bool:
        return any(is_elevated(scope) for scope in self._scopes)

    def _code_of(self, channel: str) -> str:
        entry = self._codes.get(channel)
        return entry.code if entry is not None else ""

    async def start(
        self, *, port: int = DEFAULT_REMOTE_PORT, tunnel: bool = True, telegram: bool = False
    ) -> RemoteControlStart:
        """HTTP'yi kaldır, ilk kodu üret; Telegram istenirse kayıtlı belirteçle bağlan.

        Kod üretimi ya da Telegram bağlantısı düşerse sunucu geri kapatılır: yarım açık port
        kalmaz (REPL `/rc` host'u ancak başarıda saklar).
        """
        if self._started:
            raise RemoteControlError("Uzaktan kontrol zaten çalışıyor.")
        request: dict[str, Any] = {"port": port}
        if tunnel:
            request["guvenilirTunel"] = True
        started = await self._controller.dispatch("uzak.baslat", request)
        if not started.get("ok"):
            raise RemoteControlError(str(started.get("metin") or "Uzak erişim başlatılamadı."))
        self._started = True
        self._channels = (CHANNEL_REQUEST_PWA,)
        try:
            return await self._finish_start(
                address=str(started.get("adres", "")), telegram=telegram
            )
        except BaseException:
            await self.stop()
            raise

    async def _finish_start(self, *, address: str, telegram: bool) -> RemoteControlStart:
        warnings: list[str] = []
        telegram_ok = False
        if telegram:
            telegram_ok = await self.connect_telegram()
            if not telegram_ok:
                warnings.append(TEXT_TELEGRAM_MISSING)
        if self.needs_desktop_approval:
            elevated = ", ".join(sorted(s for s in self._scopes if is_elevated(s)))
            warnings.append(TEXT_ELEVATED_SCOPES.format(scopes=elevated))
        if self._approval_hours > 0:
            status = await self._controller.dispatch("uzak.durum", {})
            if not status.get("onayYetkisiIste"):
                warnings.append(TEXT_TRUST_SETTING_OFF)
        code, expires = await self.new_code()
        return RemoteControlStart(
            address=address,
            code=code,
            expires_at=expires,
            scopes=tuple(sorted(self._scopes)),
            needs_desktop_approval=self.needs_desktop_approval,
            telegram=telegram_ok,
            warnings=tuple(warnings),
            telegram_code=self.telegram_code,
        )

    async def connect_telegram(self) -> bool:
        """Anahtarlıktaki belirteçle Telegram köprüsünü bağla ve Telegram kodunu üret.

        Belirteç yoksa `False` (HTTP yüzü etkilenmez). Bağlıysa ikinci çağrı kodu yenilemez.
        """
        if not self._started:
            raise RemoteControlError("Uzaktan kontrol çalışmıyor; önce başlat.")
        connected = await self._controller.dispatch("uzak.telegram_baglan", {})
        if not connected.get("ok"):
            return False
        if CHANNEL_REQUEST_TELEGRAM not in self._channels:
            self._channels = (*self._channels, CHANNEL_REQUEST_TELEGRAM)
        if CHANNEL_REQUEST_TELEGRAM not in self._codes:
            await self.new_code(CHANNEL_REQUEST_TELEGRAM)
        return True

    async def new_code(self, channel: str = CHANNEL_REQUEST_PWA) -> tuple[str, float]:
        """Verilen kanal için yeni eşleştirme kodu; eskisi kullanılmadıysa 2 dakikada düşer."""
        if not self._started:
            raise RemoteControlError("Uzaktan kontrol çalışmıyor; önce başlat.")
        request: dict[str, Any] = {"kanal": channel, "kapsamlar": sorted(self._scopes)}
        if self._approval_hours > 0:
            request["onaySaat"] = self._approval_hours
        result = await self._controller.dispatch("uzak.eslestir_baslat", request)
        if not result.get("ok"):
            raise RemoteControlError(str(result.get("metin") or "Eşleştirme kodu üretilemedi."))
        entry = PairingCode(channel, str(result["kod"]), float(result["bitis"]))
        self._codes = {**self._codes, channel: entry}
        return entry.code, entry.expires_at

    def code_expired(self, now: float) -> bool:
        """Herhangi bir kanalın kodu süresini doldurdu mu?"""
        return any(now > entry.expires_at for entry in self._codes.values())

    async def renew_codes(self, *, now: float) -> list[PairingCode]:
        """Eksik ya da süresi dolmuş kanal kodlarını yenile; onay bekleyen kod dokunulmaz.

        Reddedilen cihazın kanalı kodsuz kalır, süresi dolan kod düşer: ikisi de burada
        tamamlanır. Kodu girmiş ve terminal onayı bekleyen cihazın kodu yenilenmez (soru askıda).
        """
        renewed: list[PairingCode] = []
        for channel in self._channels:
            entry = self._codes.get(channel)
            if entry is not None and now <= entry.expires_at:
                continue
            if entry is not None and self._controller.awaiting_approval(entry.code):
                continue
            await self.new_code(channel)
            renewed.append(self._codes[channel])
        return renewed

    def awaiting_code(self) -> PairingCode | None:
        """Kodu girilmiş ve onay bekleyen kanal kodu (yoksa `None`)."""
        for entry in self._codes.values():
            if self._controller.awaiting_approval(entry.code):
                return entry
        return None

    async def approve_pending(self) -> bool:
        """Kodu girmiş cihazı bu terminalden onayla (yüksek yetkili kapsam ve Telegram'da)."""
        pending = self.awaiting_code()
        if pending is None:
            return False
        result = await self._controller.dispatch("uzak.eslestir_onayla", {"kod": pending.code})
        return bool(result.get("ok"))

    async def reject_pending(self) -> bool:
        """Kodu girmiş ama onaylanmamış cihazı reddet; kanal kodu düşer (`renew_codes` yeniler)."""
        pending = self.awaiting_code()
        if pending is None:
            return False
        result = await self._controller.dispatch("uzak.eslestir_reddet", {"kod": pending.code})
        self._codes = {k: v for k, v in self._codes.items() if k != pending.channel}
        return bool(result.get("ok"))

    async def snapshot(self) -> RemoteControlSnapshot:
        status = await self._controller.dispatch("uzak.durum", {})
        pending = await self._controller.dispatch("uzak.bekleyen", {})
        tasks = await self._controller.dispatch("uzak.gorevler", {})
        last = status.get("sonEslesen") or {}
        awaiting = self.awaiting_code()
        return RemoteControlSnapshot(
            listening=bool(status.get("dinliyor")),
            address=str(status.get("adres", "")),
            device_count=int(status.get("cihazSayisi", 0)),
            last_paired=str(last.get("ad", "")),
            last_paired_at=float(last.get("zaman", 0.0)),
            pending=tuple(
                PendingApproval(
                    question_id=str(item.get("soruId", "")),
                    title=str(item.get("baslik", "")),
                    target=str(item.get("hedef", "")),
                    is_approval=bool(item.get("onay")),
                )
                for item in pending.get("sorular", [])
            ),
            tasks=tuple(
                TaskLine(
                    run_id=str(item.get("runId", "")),
                    state=str(item.get("state", "")),
                    summary=str(item.get("summary", "")),
                )
                for item in tasks.get("gorevler", [])
            ),
            awaiting_device=(
                self._controller.awaiting_approval(awaiting.code) if awaiting else None
            )
            or "",
        )

    @staticmethod
    def changes(previous: RemoteControlSnapshot, current: RemoteControlSnapshot) -> list[str]:
        """İki fotoğraf arasında kullanıcıya söylenecekler; saf, sırasız değil."""
        lines: list[str] = []
        if current.awaiting_device and current.awaiting_device != previous.awaiting_device:
            lines.append(TEXT_AWAITING.format(name=current.awaiting_device))
        if current.last_paired and current.last_paired_at != previous.last_paired_at:
            lines.append(TEXT_PAIRED.format(name=current.last_paired))
        seen = {item.question_id for item in previous.pending}
        for item in current.pending:
            if item.question_id in seen:
                continue
            target = f" ({item.target})" if item.target else ""
            template = TEXT_APPROVAL if item.is_approval else TEXT_QUESTION
            lines.append(template.format(title=item.title or "işlem", target=target))
        states = {task.run_id: task.state for task in previous.tasks}
        for task in current.tasks:
            if states.get(task.run_id) != task.state:
                lines.append(
                    TEXT_TASK.format(run_id=task.run_id, state=task.state, summary=task.summary)
                )
        return lines

    async def stop(self) -> None:
        if not self._started:
            return
        self._started = False
        self._codes, self._channels = {}, ()
        await self._controller.dispatch("uzak.durdur", {})
        await self._controller.aclose()
