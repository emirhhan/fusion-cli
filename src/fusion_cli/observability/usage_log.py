"""Kalıcı kullanım günlüğü — `/usage`, `fusion usage`, `fusion insights` (P-056).

`CostTracker` oturum ömürlüdür; "son 24 saat / 7 gün ne harcadım, hangi alt ajan, hangi
MCP sunucusu" sorusu için kayıt diske yazılmalıdır. Claude Code `/usage` (attribution:
subagents/MCP/skills) ve `/insights` örnek alınmıştır.

Ne yazılır: zaman, oturum kimliği, rol, model, alt ajan kimliği, token, maliyet, arka plan
bayrağı; MCP araç çağrıları (sunucu adı) ve yüklenen beceriler. İSTEM METNİ, ARAÇ
ARGÜMANI ya da ÇIKTI yazılmaz: günlük kimin ne sorduğunu değil, ne harcandığını tutar.
`runtime.usage_log: false` ile tamamen kapatılır. Dosya yazılamazsa günlük sessizce
devre dışı kalır; uygulama tam çalışır (RULES: gözlemlenebilirlik opsiyonel).

Ölçüldü (31 Ekim): `/cost` yalnız bu oturumu gösteriyordu; pencereli kırılım, atıf ve
HTML rapor yoktu.
"""

from __future__ import annotations

import json
import logging
import secrets
import time
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import MISSING, asdict, dataclass, field, fields
from pathlib import Path

from ..config.models import Config
from ..core.events import Event, ModelCallFinished, SkillLoaded, ToolExecuted, ToolOutcome
from ..core.mcp_tool_names import mcp_server_of as _core_mcp_server_of
from ..core.types import TokenUsage

_LOG = logging.getLogger(__name__)

#: `memory_dir` altındaki günlük dosyası.
USAGE_LOG_NAME = "usage.jsonl"
#: Bundan eski satırlar açılışta budanır.
RETENTION_DAYS = 90
#: Özet pencereleri (ad, saniye). "oturum" ayrıca hesaplanır.
WINDOWS: tuple[tuple[str, float], ...] = (
    ("son 24 saat", 24 * 3600.0),
    ("son 7 gün", 7 * 24 * 3600.0),
    ("son 30 gün", 30 * 24 * 3600.0),
)

KIND_MODEL = "model"
KIND_TOOL = "arac"
KIND_SKILL = "beceri"


@dataclass(frozen=True, slots=True)
class UsageRecord:
    """Tek günlük satırı. `tur` kayıt türüdür; alanların çoğu türe göre boş kalır."""

    ts: float
    oturum: str
    tur: str
    rol: str = ""
    model: str = ""
    ajan: str = ""
    arka_plan: bool = False
    ok: bool = True
    girdi_token: int = 0
    cikti_token: int = 0
    maliyet_usd: float = 0.0
    maliyet_bilinen: bool = False
    #: `arac` türünde araç adı; MCP aracında `sunucu` dolu.
    arac: str = ""
    sunucu: str = ""
    #: `beceri` türünde yüklenen becerinin nitelikli adı.
    beceri: str = ""

    @property
    def usage(self) -> TokenUsage:
        return TokenUsage(
            prompt_tokens=self.girdi_token,
            completion_tokens=self.cikti_token,
            cost_usd=self.maliyet_usd,
            prompt_measured=True,
            completion_measured=True,
            cost_known=self.maliyet_bilinen,
        )


def usage_log_path(config: Config) -> Path:
    return config.memory_dir / USAGE_LOG_NAME


class UsageLog:
    """Olay veriyolu dinleyicisi: model/araç/beceri olaylarını JSONL'e ekler.

    `session_id` bu sürecin oturum kimliğidir; olay kendi `session_id`'sini taşıyorsa o
    yazılır. Aynı dosyaya birden çok süreç ekleyebilir (satır başına `O_APPEND`).
    """

    def __init__(
        self,
        path: Path,
        *,
        session_id: str | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._path = path
        self._clock = clock
        self.session_id = session_id or new_session_id("oturum")
        self._disabled = False

    @property
    def path(self) -> Path:
        return self._path

    # ----------------------------------------------------------------- yazma #

    def handle(self, event: Event) -> None:
        record = self._record_for(event)
        if record is not None:
            self.append(record)

    def _record_for(self, event: Event) -> UsageRecord | None:
        session = event.session_id or self.session_id
        if isinstance(event, ModelCallFinished):
            usage = event.result.usage
            return UsageRecord(
                ts=self._clock(),
                oturum=session,
                tur=KIND_MODEL,
                rol=event.role,
                model=event.result.served_by or event.result.model or event.requested_model,
                ajan=event.agent_id,
                arka_plan=event.background,
                ok=event.result.ok,
                girdi_token=usage.prompt_tokens,
                cikti_token=usage.completion_tokens,
                maliyet_usd=usage.cost_usd,
                maliyet_bilinen=usage.cost_known,
            )
        if isinstance(event, ToolExecuted):
            server = mcp_server_of(event.name)
            return UsageRecord(
                ts=self._clock(),
                oturum=session,
                tur=KIND_TOOL,
                ajan=event.agent_id,
                ok=event.outcome is ToolOutcome.OK,
                arac=event.name,
                sunucu=server,
            )
        if isinstance(event, SkillLoaded):
            return UsageRecord(
                ts=self._clock(),
                oturum=session,
                tur=KIND_SKILL,
                ajan=event.agent_id,
                beceri=event.qualified_name,
            )
        return None

    def append(self, record: UsageRecord) -> None:
        if self._disabled:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
        except OSError as error:
            # Bir kez uyar, sonra sus: günlük işin kendisini durdurmaz.
            self._disabled = True
            _LOG.warning("Kullanım günlüğü yazılamadı, kapatıldı", extra={"hata": str(error)})

    # ----------------------------------------------------------------- okuma #

    def read(self, *, since: float | None = None) -> tuple[UsageRecord, ...]:
        return tuple(read_records(self._path, since=since))

    def prune(self, *, keep_days: int = RETENTION_DAYS) -> int:
        """Eski satırları at; atılan satır sayısını döndür. Okunamayan dosya dokunulmaz.

        Ölçüldü (31 Ekim): her açılışta dosya `write_text` ile yerinde yeniden yazılıyordu;
        aynı anda `O_APPEND` ile ekleyen başka sürecin (CI'da paralel `fusion agent`,
        masaüstü + terminal) satırı kaybolabiliyor, yazma yarıda kalırsa dosya bozuluyordu.
        Artık satırlar eklenme sırasında olduğundan ilk satır eşiği geçmiyorsa hiç
        yazılmaz; gerekirse geçici dosyaya yazılır, okumadan sonra eklenen kuyruk
        aktarılır ve `Path.replace` ile atomik değiştirilir.
        """
        if not self._path.is_file():
            return 0
        cutoff = self._clock() - keep_days * 86400.0
        try:
            data = self._path.read_bytes()
        except OSError:
            return 0
        lines = data.decode("utf-8", errors="replace").splitlines()
        if not lines or _line_ts(lines[0]) >= cutoff:
            return 0
        kept = [line for line in lines if _line_ts(line) >= cutoff]
        target = self._path.with_name(f".{self._path.name}.{secrets.token_hex(4)}.tmp")
        try:
            self._write_kept(target, kept)
            with self._path.open("rb") as source:
                source.seek(len(data))
                tail = source.read()
            if tail:
                with target.open("ab") as handle:
                    handle.write(tail)
            target.replace(self._path)
        except OSError:
            target.unlink(missing_ok=True)
            return 0
        return len(lines) - len(kept)

    def _write_kept(self, target: Path, kept: list[str]) -> None:
        target.write_text("".join(f"{line}\n" for line in kept), encoding="utf-8")


def new_session_id(prefix: str) -> str:
    """Süreç yeniden başlasa da çakışmayan oturum kimliği (zaman + rastgele ek)."""
    return f"{prefix}-{int(time.time() * 1000)}-{secrets.token_hex(3)}"


def mcp_server_of(tool_name: str) -> str:
    """`mcp__github__create_issue` (ve eski `github__create_issue`) → `github`; yerleşikte boş."""
    return _core_mcp_server_of(tool_name)


def _line_ts(line: str) -> float:
    try:
        return float(json.loads(line).get("ts", 0.0))
    except (ValueError, AttributeError):
        return 0.0


def read_records(path: Path, *, since: float | None = None) -> Iterator[UsageRecord]:
    """JSONL'i satır satır oku; bozuk satır atlanır (günlük teşhis verisidir, iş verisi değil)."""
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except ValueError:
            continue
        record = _record_from(raw)
        if record is None:
            continue
        if since is not None and record.ts < since:
            continue
        yield record


#: Alan tipi → kabul edilen JSON tipleri. `bool` `int`'in alt sınıfı olduğundan ayrı denetlenir.
_ACCEPTED: dict[str, tuple[type, ...]] = {
    "float": (int, float),
    "int": (int,),
    "str": (str,),
    "bool": (bool,),
}
_FIELD_TYPES: dict[str, str] = {item.name: str(item.type) for item in fields(UsageRecord)}
_REQUIRED = frozenset(item.name for item in fields(UsageRecord) if item.default is MISSING)


def _record_from(raw: object) -> UsageRecord | None:
    """JSON satırını tipine göre doğrulayıp kayda çevir; uymayan satır None.

    Ölçüldü (31 Ekim): `UsageRecord(**satır)` tipleri denetlemiyordu; `ts` metin olan bir
    satır `summarize`/`read(since=...)` içinde `TypeError` atıp `/usage`'ı düşürüyordu.
    """
    if not isinstance(raw, dict):
        return None
    values: dict[str, object] = {}
    for key, value in raw.items():
        kind = _FIELD_TYPES.get(key)
        if kind is None:
            continue
        accepted = _ACCEPTED.get(kind, ())
        if kind != "bool" and isinstance(value, bool):
            return None
        if not isinstance(value, accepted):
            return None
        values[key] = float(value) if isinstance(value, int) and kind == "float" else value
    if not _REQUIRED.issubset(values):
        return None
    return UsageRecord(**values)  # type: ignore[arg-type]


def open_usage_log(config: Config, *, session_id: str | None = None) -> UsageLog | None:
    """Ayar açıksa günlüğü kur ve eski satırları buda; kapalıysa None."""
    if not getattr(config.runtime, "usage_log", True):
        return None
    log = UsageLog(usage_log_path(config), session_id=session_id)
    log.prune()
    return log


# --------------------------------------------------------------------- özet #


@dataclass
class UsageBucket:
    """Bir pencere ya da atıf satırının toplamı."""

    calls: int = 0
    usage: TokenUsage = field(default_factory=TokenUsage)
    failed: int = 0

    def add(self, record: UsageRecord) -> None:
        self.calls += 1
        if not record.ok:
            self.failed += 1
        self.usage = record.usage if self.calls == 1 else self.usage + record.usage

    @property
    def cost_complete(self) -> bool:
        return self.calls == 0 or self.usage.cost_known


@dataclass(frozen=True, slots=True)
class AttributionRow:
    label: str
    calls: int
    tokens: int
    cost_usd: float


@dataclass(frozen=True, slots=True)
class UsageSummary:
    """`/usage`, `kullanim.durum` ve HTML raporun ortak veri modeli."""

    #: (pencere adı, toplam) — ilk eleman "bu oturum".
    windows: tuple[tuple[str, UsageBucket], ...]
    by_model: tuple[AttributionRow, ...]
    #: Ana ajan / alt ajan / arka plan kırılımı (seçili pencere).
    by_actor: tuple[AttributionRow, ...]
    #: MCP sunucusu başına araç çağrısı sayısı.
    mcp_calls: tuple[tuple[str, int], ...]
    #: Yüklenen beceri → sayı.
    skills: tuple[tuple[str, int], ...]
    window_label: str
    record_count: int


def summarize(
    records: Iterable[UsageRecord],
    *,
    now: float,
    session_id: str,
    window_s: float = WINDOWS[1][1],
    window_label: str = WINDOWS[1][0],
) -> UsageSummary:
    """Kayıtları pencerelere ve atıf satırlarına indir. Kırılımlar `window_s` içindir."""
    items = tuple(records)
    windows: list[tuple[str, UsageBucket]] = [("bu oturum", UsageBucket())]
    windows.extend((label, UsageBucket()) for label, _ in WINDOWS)
    by_model: dict[str, UsageBucket] = defaultdict(UsageBucket)
    by_actor: dict[str, UsageBucket] = defaultdict(UsageBucket)
    mcp: dict[str, int] = defaultdict(int)
    skills: dict[str, int] = defaultdict(int)
    for record in items:
        age = now - record.ts
        in_window = age <= window_s
        if record.tur == KIND_TOOL:
            if record.sunucu and in_window:
                mcp[record.sunucu] += 1
            continue
        if record.tur == KIND_SKILL:
            if in_window:
                skills[record.beceri] += 1
            continue
        if record.oturum == session_id:
            windows[0][1].add(record)
        for (_label, seconds), (_, bucket) in zip(WINDOWS, windows[1:], strict=True):
            if age <= seconds:
                bucket.add(record)
        if in_window:
            by_model[record.model or "bilinmeyen"].add(record)
            by_actor[_actor_label(record)].add(record)
    return UsageSummary(
        windows=tuple(windows),
        by_model=_rows(by_model),
        by_actor=_rows(by_actor),
        mcp_calls=tuple(sorted(mcp.items(), key=lambda item: -item[1])),
        skills=tuple(sorted(skills.items(), key=lambda item: -item[1])),
        window_label=window_label,
        record_count=len(items),
    )


def _actor_label(record: UsageRecord) -> str:
    if record.ajan:
        return "alt ajan"
    if record.arka_plan:
        return "arka plan (hakem, sentez, ders)"
    return "ana ajan"


def _rows(buckets: dict[str, UsageBucket]) -> tuple[AttributionRow, ...]:
    rows = (
        AttributionRow(label, bucket.calls, bucket.usage.total_tokens, bucket.usage.cost_usd)
        for label, bucket in buckets.items()
    )
    return tuple(sorted(rows, key=lambda row: -row.tokens))
