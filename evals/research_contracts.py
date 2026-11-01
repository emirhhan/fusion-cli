"""Görev/tekrar kapsamını ve ham bütçe kanıtını tek sözleşmede doğrular."""

from __future__ import annotations

import math
import re
from collections import Counter

_DIGEST = re.compile(r"[a-f0-9]{64}\Z")


def valid_digest(value: object) -> bool:
    """Yalnız kanonik SHA-256 metni ölçülmüş özet olabilir."""
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def has_execution_coverage(
    task_ids: tuple[str, ...], repeat: int, execution_ids: tuple[tuple[str, int | None], ...]
) -> bool:
    """Her beklenen görev/tekrar çifti tam bir kez bulunmalı."""
    if not task_ids or len(set(task_ids)) != len(task_ids) or type(repeat) is not int or repeat < 1:
        return False
    if any(type(index) is not int for _, index in execution_ids):
        return False
    expected = Counter((identity, index) for identity in task_ids for index in range(1, repeat + 1))
    return Counter(execution_ids) == expected


def has_task_config_coverage(
    task_ids: tuple[str, ...],
    repeat: int,
    execution_ids: tuple[tuple[str, int], ...],
    configs: tuple[tuple[str, str], ...],
) -> bool:
    """Her gerçek execution aynı sırada kendi ölçülmüş config özetini taşımalı."""
    return (
        has_execution_coverage(task_ids, repeat, execution_ids)
        and tuple(identity for identity, _ in configs)
        == tuple(identity for identity, _ in execution_ids)
        and all(valid_digest(digest) for _, digest in configs)
    )


def parse_task_budgets(raw: object) -> tuple[tuple[str, int, float], ...]:
    """Dönüşümden önce ham türleri doğrula; eski eksik alan bilinmiyor kalır."""
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise ValueError("Görev bütçeleri liste olmalı")
    budgets = []
    for item in raw:
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            raise ValueError("Görev bütçe kaydı tam üç alan içermeli")
        identity, calls, timeout = item
        if (
            not isinstance(identity, str)
            or not identity
            or type(calls) is not int
            or calls <= 0
            or type(timeout) not in (int, float)
            or timeout <= 0
            or not math.isfinite(timeout)
        ):
            raise ValueError("Görev bütçesi kimlik, pozitif tam çağrı ve sonlu süre içermeli")
        budgets.append((identity, calls, float(timeout)))
    return tuple(budgets)


def parse_execution_ids(raw: object) -> tuple[tuple[str, int], ...]:
    """Tekrar kimliği boolean veya metinden sessizce üretilemez."""
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise ValueError("Çalıştırma kimlikleri liste olmalı")
    values = []
    for item in raw:
        if (
            not isinstance(item, (list, tuple))
            or len(item) != 2
            or not isinstance(item[0], str)
            or not item[0]
            or type(item[1]) is not int
            or item[1] < 1
        ):
            raise ValueError("Çalıştırma kimliği görev ve pozitif tekrar sayısı içermeli")
        values.append((item[0], item[1]))
    return tuple(values)
