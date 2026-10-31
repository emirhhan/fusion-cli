"""Kaydedilmiş iş akışları ve koşu kayıtları (P-062).

- Tanımlar: proje `.fusion/workflows/<ad>.json`, kullanıcı `<yapılandırma>/workflows/<ad>.json`
  (Claude Code `.claude/workflows/` ve `~/.claude/workflows/`). Aynı ad projede varsa
  proje kazanır.
- Koşular: `.fusion/workflows/kosular/<kimlik>.json` — `/workflows`, `fusion workflows`
  ve masaüstü panosu buradan okur. İptal isteği ayrı bir `<kimlik>.iptal` işaret
  dosyasıdır: koşu kaydını yazan süreçle yarışmaz, başka bir terminalden de verilebilir.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from ...core.orchestration_events import WorkflowNodeView
from ...tools.files import atomic_write
from .workflow_spec import NAME_PATTERN, WorkflowError, WorkflowSpec, parse_workflow

_LOG = logging.getLogger(__name__)

PROJECT_DIR = Path(".fusion") / "workflows"
RUNS_DIRNAME = "kosular"
DEFINITION_SUFFIX = ".json"
CANCEL_SUFFIX = ".iptal"
#: Saklanan en fazla koşu kaydı; eskiler silinir.
MAX_RUNS = 50
#: `/workflows` alt komutları: bu adla kayıtlı akış hiç çalıştırılamazdı (komut gölgeler).
RESERVED_NAMES = frozenset(
    {"liste", "list", "goster", "show", "iptal", "cancel", "stop", "sil", "delete"}
)
#: Bitmiş sayılan koşu durumları.
FINISHED = frozenset({"tamam", "yarim", "iptal", "hata"})


@dataclass(frozen=True, slots=True)
class SavedWorkflow:
    name: str
    #: proje | kullanici
    scope: str
    path: Path
    description: str = ""


@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: str
    name: str
    status: str
    started_at: float
    finished_at: float = 0.0
    phase: str = ""
    agents_started: int = 0
    agents_limit: int = 0
    nodes: tuple[WorkflowNodeView, ...] = ()
    message: str = ""
    pid: int = 0
    report: str = ""


class WorkflowStore:
    """Tanım ve koşu dosyalarının tek erişim noktası (senkron; çağıran thread'e alır)."""

    def __init__(self, root: Path, user_dir: Path | None = None) -> None:
        self.project_dir = root / PROJECT_DIR
        self.user_dir = user_dir
        self.runs_dir = self.project_dir / RUNS_DIRNAME

    # -- tanımlar --------------------------------------------------------- #

    def definitions(self) -> list[SavedWorkflow]:
        found: dict[str, SavedWorkflow] = {}
        for scope, directory in (("kullanici", self.user_dir), ("proje", self.project_dir)):
            if directory is None or not directory.is_dir():
                continue
            for path in sorted(directory.glob(f"*{DEFINITION_SUFFIX}")):
                name = path.stem
                if not NAME_PATTERN.match(name):
                    continue
                found[name] = SavedWorkflow(name, scope, path, _description(path))
        return [found[name] for name in sorted(found)]

    def find(self, name: str) -> SavedWorkflow | None:
        return next((item for item in self.definitions() if item.name == name.strip()), None)

    def load(self, name: str) -> WorkflowSpec:
        saved = self.find(name)
        if saved is None:
            known = ", ".join(item.name for item in self.definitions()) or "yok"
            raise WorkflowError(f"'{name}' adlı kayıtlı iş akışı yok (kayıtlı: {known}).")
        try:
            raw = saved.path.read_text(encoding="utf-8")
        except OSError as error:
            raise WorkflowError(f"{saved.path} okunamadı: {error.strerror}.") from error
        return parse_workflow(raw, fallback_name=saved.name)

    def save(self, spec: WorkflowSpec, *, scope: str = "proje", replace: bool = True) -> Path:
        """Tanımı yaz. `replace=False`: aynı adlı FARKLI tanım varsa `WorkflowError`."""
        path = self.ensure_savable(spec, scope=scope, replace=replace)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, spec.source + "\n")
        return path

    def ensure_savable(self, spec: WorkflowSpec, *, scope: str = "proje", replace: bool) -> Path:
        """Kaydın gideceği yol; ayrılmış ad ya da (replace=False) çakışan tanım reddedilir.

        Ölçüldü (31 Ekim): `kaydet: true` kullanıcının elle yazdığı aynı adlı proje
        akışını onaysız eziyordu; 'goster'/'sil' adlı akış `/workflows`'ta çalıştırılamıyordu.
        """
        if spec.name in RESERVED_NAMES:
            raise WorkflowError(
                f"'{spec.name}' /workflows için ayrılmış bir kelime; tanıma başka bir 'ad' ver."
            )
        directory = self.project_dir if scope == "proje" else self.user_dir
        if directory is None:
            raise WorkflowError("Kullanıcı iş akışı dizini bilinmiyor; 'proje' kapsamını kullan.")
        path = directory / f"{spec.name}{DEFINITION_SUFFIX}"
        if not replace and path.is_file():
            try:
                same = path.read_text(encoding="utf-8").strip() == spec.source.strip()
            except OSError:
                same = False
            if not same:
                raise WorkflowError(
                    f"'{spec.name}' adlı farklı bir iş akışı zaten kayıtlı ({path}); üzerine "
                    f"yazılmadı. Başka bir 'ad' ver ya da önce '/workflows sil {spec.name}'."
                )
        return path

    def delete(self, name: str) -> Path | None:
        saved = self.find(name)
        if saved is None:
            return None
        saved.path.unlink(missing_ok=True)
        return saved.path

    # -- koşular ---------------------------------------------------------- #

    def write_run(self, record: RunRecord) -> None:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        atomic_write(self._run_path(record.run_id), json.dumps(asdict(record), ensure_ascii=False))
        if record.status in FINISHED:
            self._cancel_path(record.run_id).unlink(missing_ok=True)
            self._prune()

    def runs(self, limit: int = MAX_RUNS) -> list[RunRecord]:
        if not self.runs_dir.is_dir():
            return []
        paths = sorted(
            self.runs_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True
        )
        records = [record for path in paths[:limit] if (record := _read_run(path)) is not None]
        return [_mark_orphan(record) for record in records]

    def run(self, run_id: str) -> RunRecord | None:
        if not _safe_id(run_id):
            return None
        record = _read_run(self._run_path(run_id))
        return _mark_orphan(record) if record is not None else None

    def request_cancel(self, run_id: str) -> bool:
        """Koşan bir koşuya iptal işareti bırak; koşu yoksa ya da bittiyse False."""
        record = self.run(run_id)
        if record is None or record.status in FINISHED:
            return False
        self._cancel_path(run_id).touch()
        return True

    def cancel_requested(self, run_id: str) -> bool:
        return self._cancel_path(run_id).exists()

    def _run_path(self, run_id: str) -> Path:
        return self.runs_dir / f"{run_id}.json"

    def _cancel_path(self, run_id: str) -> Path:
        return self.runs_dir / f"{run_id}{CANCEL_SUFFIX}"

    def _prune(self) -> None:
        paths = sorted(self.runs_dir.glob("*.json"), key=lambda path: path.stat().st_mtime)
        for path in paths[: max(0, len(paths) - MAX_RUNS)]:
            with contextlib.suppress(OSError):
                path.unlink()


def _safe_id(run_id: str) -> bool:
    return bool(run_id) and run_id.isalnum() and len(run_id) <= 32


def _description(path: Path) -> str:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "(okunamadı)"
    if isinstance(raw, dict):
        return str(raw.get("aciklama") or raw.get("description") or "")[:160]
    return ""


def _read_run(path: Path) -> RunRecord | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        _LOG.warning("iş akışı koşu kaydı okunamadı", extra={"yol": str(path), "hata": str(error)})
        return None
    if not isinstance(raw, dict):
        return None
    nodes = tuple(
        WorkflowNodeView(**{key: str(node.get(key, "")) for key in WorkflowNodeView.__slots__})
        for node in raw.get("nodes", ())
        if isinstance(node, dict)
    )
    try:
        return RunRecord(
            run_id=str(raw["run_id"]),
            name=str(raw.get("name", "")),
            status=str(raw.get("status", "")),
            started_at=float(raw.get("started_at", 0.0)),
            finished_at=float(raw.get("finished_at", 0.0)),
            phase=str(raw.get("phase", "")),
            agents_started=int(raw.get("agents_started", 0)),
            agents_limit=int(raw.get("agents_limit", 0)),
            nodes=nodes,
            message=str(raw.get("message", "")),
            pid=int(raw.get("pid", 0)),
            report=str(raw.get("report", "")),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _mark_orphan(record: RunRecord) -> RunRecord:
    """Koşuyu yürüten süreç kapandıysa 'calisiyor' kaydı yarım sayılır."""
    if record.status in FINISHED or record.pid <= 0 or _alive(record.pid):
        return record
    return replace(record, status="yarim", message="Koşuyu yürüten süreç kapandı.")


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
