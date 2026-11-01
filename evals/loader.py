"""Görev setini YAML/JSON dosyasından okuyan doğrulayıcı.

Set formatı: kök öğe `tasks` listesidir. Her görev `id`, `request` ve tek bir
`criterion` içerir. Bilinmeyen/eksik alan sessizce yok sayılmaz; `EvalError` ile
anlaşılır biçimde reddedilir (RULES.md "Yapılandırma").
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import cast

import yaml

from evals.tasks import (
    CriterionKind,
    EvalSuite,
    EvalTask,
    SuccessCriterion,
    SuiteMetadata,
    TaskBudget,
)
from fusion_cli.core.errors import EvalError

#: Her ölçüt türünün gerektirdiği alan ve o alanı okuyan dönüştürücü.
_CRITERION_FIELDS: dict[CriterionKind, tuple[str, str]] = {
    CriterionKind.EXIT_CODE: ("expected_exit_code", "int"),
    CriterionKind.FILE_CHANGED: ("expected_path", "str"),
    CriterionKind.FILE_UNCHANGED: ("expected_path", "str"),
    CriterionKind.KEYWORD: ("keyword", "str|list"),
}


def load_tasks(path: Path) -> tuple[EvalTask, ...]:
    """Mevcut çağıranlar için tek set yükleme yolundan görevleri döndür."""
    return load_suite(path).tasks


def load_suite(path: Path, *, allowed_splits: frozenset[str] | None = None) -> EvalSuite:
    """Görev setini dosyadan okur ve doğrular.

    YAML üst kümesi JSON'u da kapsar; tek çözümleyici ikisini de okur.
    """

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise EvalError(f"görev seti okunamadı: {path} — {exc}") from exc

    if not isinstance(raw, dict) or "tasks" not in raw:
        raise EvalError(f"görev seti kökünde 'tasks' listesi bekleniyordu: {path}")
    raw_tasks = raw["tasks"]
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise EvalError(f"'tasks' boş olmayan bir liste olmalı: {path}")

    namespace = raw.get("namespace")
    if namespace is not None and not isinstance(namespace, str):
        raise EvalError("namespace metin olmalı")
    split = raw.get("split")
    if split is not None and split not in {"development", "validation", "blind"}:
        raise EvalError(f"bilinmeyen split: {split!r}")
    if allowed_splits is not None and split is not None and split not in allowed_splits:
        raise EvalError(f"split bu işlem için izinli değil: {split!r}")
    if split is not None:
        _guard_research_ids(raw_tasks, frozenset({split}), namespace)
    if allowed_splits is not None:
        _guard_research_ids(raw_tasks, allowed_splits, namespace)
    tasks = tuple(parse_task(item) for item in raw_tasks)
    _ensure_unique_ids(tasks)
    complete = raw.get("task6_complete")
    if complete is not None and not isinstance(complete, bool):
        raise EvalError("task6_complete boolean olmalı")
    return EvalSuite(
        tasks, SuiteMetadata(split=split, task6_complete=complete, namespace=namespace)
    )


def _ensure_unique_ids(tasks: tuple[EvalTask, ...]) -> None:
    seen: set[str] = set()
    for task in tasks:
        if task.id in seen:
            raise EvalError(f"görev kimliği yinelenmiş: {task.id!r}")
        seen.add(task.id)


def parse_task(item: object) -> EvalTask:
    """Tek bir görev sözlüğünü doğrula ve `EvalTask`a çevir (taslak kabulü de bunu kullanır)."""
    if not isinstance(item, dict):
        raise EvalError("her görev bir sözlük olmalı")
    for key in ("id", "request", "criterion"):
        if key not in item:
            raise EvalError(f"görevde zorunlu alan eksik: {key!r}")
    return EvalTask(
        id=str(item["id"]),
        request=str(item["request"]),
        criterion=parse_criterion(item["criterion"]),
        setup=_parse_setup(item.get("setup")),
        approval=_parse_approval(item.get("approval")),
        budget=_parse_budget(item.get("budget")),
        runtime_scenario=_parse_scenario(item.get("runtime_scenario")),
    )


def _parse_budget(raw: object) -> TaskBudget | None:
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) != {"max_model_calls", "timeout_s"}:
        raise EvalError("budget yalnız max_model_calls ve timeout_s içermeli")
    calls, timeout = raw["max_model_calls"], raw["timeout_s"]
    if type(calls) is not int or calls <= 0:
        raise EvalError("max_model_calls pozitif tam sayı olmalı")
    if type(timeout) not in (int, float) or not 0 < timeout < float("inf"):
        raise EvalError("timeout_s pozitif sonlu sayı olmalı")
    return TaskBudget(calls, float(timeout))


def _parse_scenario(raw: object) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.isidentifier():
        raise EvalError("runtime_scenario geçerli bir kimlik olmalı")
    return raw


def _parse_approval(raw: object) -> str:
    """Onay duruşunu doğrula. Bilinmeyen değer sessizce varsayılana düşmez."""
    if raw is None:
        return "permissive"
    value = str(raw)
    if value not in {"permissive", "strict"}:
        raise EvalError(f"bilinmeyen onay duruşu: {value!r} (permissive | strict)")
    return value


def _parse_setup(raw: object) -> dict[str, str]:
    """`setup` bloğunu yol→içerik sözlüğüne çevir. Yoksa boş."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise EvalError("'setup' bir sözlük olmalı: <yol>: <içerik>")
    return {str(yol): str(icerik) for yol, icerik in raw.items()}


def parse_criterion(raw: object) -> SuccessCriterion:
    """Ölçüt sözlüğünü doğrula ve `SuccessCriterion`a çevir."""
    if not isinstance(raw, dict) or "kind" not in raw:
        raise EvalError("ölçüt bir sözlük olmalı ve 'kind' içermeli")
    try:
        kind = CriterionKind(str(raw["kind"]))
    except ValueError as exc:
        raise EvalError(f"bilinmeyen ölçüt türü: {raw['kind']!r}") from exc

    if kind is CriterionKind.WORKSPACE_UNCHANGED:
        # Alansız ölçüt: "hiçbir dosya değişmemeli" iddiası parametre almaz.
        return SuccessCriterion(kind=kind)

    field, field_type = _CRITERION_FIELDS[kind]
    if field not in raw:
        raise EvalError(f"{kind.value} ölçütü için zorunlu alan eksik: {field!r}")
    value = raw[field]

    if field_type == "int":
        command = raw.get("command")
        return SuccessCriterion(
            kind=kind,
            expected_exit_code=int(cast(int, value)),
            command=str(command) if command is not None else None,
        )
    if field == "expected_path":
        return SuccessCriterion(kind=kind, expected_path=str(value))
    return _parse_keyword(kind, value)


def _parse_keyword(kind: CriterionKind, value: object) -> SuccessCriterion:
    """`keyword` tek bir metin ya da eşdeğerler listesi olabilir."""
    if isinstance(value, str):
        return SuccessCriterion(kind=kind, keyword=value)
    if isinstance(value, list):
        kelimeler = tuple(str(kelime) for kelime in value if str(kelime))
        if not kelimeler:
            raise EvalError("keyword listesi boş olamaz")
        return SuccessCriterion(kind=kind, keyword=kelimeler[0], alternatives=kelimeler[1:])
    raise EvalError(f"keyword bir metin ya da metin listesi olmalı: {value!r}")


def task_to_mapping(task: EvalTask) -> dict[str, object]:
    """`parse_task`ın tersi: görevi YAML'a yazılabilir sözlüğe çevir.

    Taslak kabulü görevi kullanıcı kümesine bu biçimde yazar; `load_tasks` aynı
    dosyayı geri okuyabilmelidir (gidiş-dönüş testi).
    """

    mapping: dict[str, object] = {
        "id": task.id,
        "request": task.request,
        "criterion": criterion_to_mapping(task.criterion),
    }
    if task.approval != "permissive":
        mapping["approval"] = task.approval
    if task.setup:
        mapping["setup"] = dict(task.setup)
    if task.budget is not None:
        mapping["budget"] = {
            "max_model_calls": task.budget.max_model_calls,
            "timeout_s": task.budget.timeout_s,
        }
    if task.runtime_scenario is not None:
        mapping["runtime_scenario"] = task.runtime_scenario
    return mapping


def criterion_to_mapping(criterion: SuccessCriterion) -> dict[str, object]:
    mapping: dict[str, object] = {"kind": criterion.kind.value}
    if criterion.kind is CriterionKind.EXIT_CODE:
        mapping["expected_exit_code"] = criterion.expected_exit_code
        if criterion.command is not None:
            mapping["command"] = criterion.command
    elif criterion.kind in (CriterionKind.FILE_CHANGED, CriterionKind.FILE_UNCHANGED):
        mapping["expected_path"] = criterion.expected_path
    elif criterion.kind is CriterionKind.KEYWORD:
        mapping["keyword"] = (
            [criterion.keyword, *criterion.alternatives]
            if criterion.alternatives
            else criterion.keyword
        )
    return mapping


def _guard_research_ids(
    items: list[object], allowed: frozenset[str], namespace: str | None
) -> None:
    """Kısa genel kimlik değil, araştırma ad alanı veya kabul bağlantısı korunur."""
    manifest = Path(__file__).parent / "fixtures/fusion_research/manifest.json"
    records = json.loads(manifest.read_text(encoding="utf-8"))["tasks"]
    canonical = {record["id"]: record["split"] for record in records}
    for item in items:
        for identity in _research_identities(item, namespace):
            if identity in canonical and canonical[identity] not in allowed:
                raise EvalError(f"Görev split kimliği bu işlem için izinli değil: {identity}")


def _research_identities(item: object, namespace: str | None) -> tuple[str, ...]:
    if not isinstance(item, dict):
        return ()
    identities = []
    if namespace == "fusion_research" or item.get("runtime_scenario") is not None:
        identities.append(str(item.get("id")))
    criterion = item.get("criterion")
    if isinstance(criterion, dict) and isinstance(criterion.get("command"), str):
        try:
            lexer = shlex.shlex(criterion["command"], posix=True, punctuation_chars=True)
            lexer.whitespace_split = True
            lexer.commenters = ""
            tokens = list(lexer)
        except ValueError as error:
            raise EvalError("Kabul komutunun sözdizimi geçersiz") from error
        module = "evals.fixtures.fusion_research.acceptance"
        for position, token in enumerate(tokens[:-1]):
            if token == module:
                identities.append(tokens[position + 1])
    return tuple(identities)
