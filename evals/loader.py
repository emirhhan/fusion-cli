"""Görev setini YAML/JSON dosyasından okuyan doğrulayıcı.

Set formatı: kök öğe `tasks` listesidir. Her görev `id`, `request` ve tek bir
`criterion` içerir. Bilinmeyen/eksik alan sessizce yok sayılmaz; `EvalError` ile
anlaşılır biçimde reddedilir (RULES.md "Yapılandırma").
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import yaml

from evals.tasks import CriterionKind, EvalTask, SuccessCriterion
from fusion_cli.core.errors import EvalError

#: Her ölçüt türünün gerektirdiği alan ve o alanı okuyan dönüştürücü.
_CRITERION_FIELDS: dict[CriterionKind, tuple[str, str]] = {
    CriterionKind.EXIT_CODE: ("expected_exit_code", "int"),
    CriterionKind.FILE_CHANGED: ("expected_path", "str"),
    CriterionKind.KEYWORD: ("keyword", "str"),
}


def load_tasks(path: Path) -> tuple[EvalTask, ...]:
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

    tasks = tuple(_parse_task(item) for item in raw_tasks)
    _ensure_unique_ids(tasks)
    return tasks


def _ensure_unique_ids(tasks: tuple[EvalTask, ...]) -> None:
    seen: set[str] = set()
    for task in tasks:
        if task.id in seen:
            raise EvalError(f"görev kimliği yinelenmiş: {task.id!r}")
        seen.add(task.id)


def _parse_task(item: object) -> EvalTask:
    if not isinstance(item, dict):
        raise EvalError("her görev bir sözlük olmalı")
    for key in ("id", "request", "criterion"):
        if key not in item:
            raise EvalError(f"görevde zorunlu alan eksik: {key!r}")
    return EvalTask(
        id=str(item["id"]),
        request=str(item["request"]),
        criterion=_parse_criterion(item["criterion"]),
        setup=_parse_setup(item.get("setup")),
        approval=_parse_approval(item.get("approval")),
    )


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


def _parse_criterion(raw: object) -> SuccessCriterion:
    if not isinstance(raw, dict) or "kind" not in raw:
        raise EvalError("ölçüt bir sözlük olmalı ve 'kind' içermeli")
    try:
        kind = CriterionKind(str(raw["kind"]))
    except ValueError as exc:
        raise EvalError(f"bilinmeyen ölçüt türü: {raw['kind']!r}") from exc

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
    return SuccessCriterion(kind=kind, keyword=str(value))
