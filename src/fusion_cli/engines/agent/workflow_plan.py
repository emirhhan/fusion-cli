"""İş akışı tanımının girdilerle somut plana açılması ve istem doldurma (P-062).

Açılmış plan çalıştırılmadan önce bütün ajan düğümlerini bilir: bütçe uyarısı ("bu koşu
N ajan başlatacak") ve `/workflows` panosundaki "bekliyor" satırları buradan gelir.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from .workflow_spec import (
    MAX_ITEMS,
    PLACEHOLDER,
    AgentOptions,
    AgentStep,
    EachStep,
    GroupStep,
    Step,
    WorkflowError,
    WorkflowSpec,
    coerce_input,
)

#: Başka bir adımın sonucu isteme girerken kırpılır: bağlam patlamasın.
RESULT_INSERT_CHARS = 6_000


@dataclass(frozen=True, slots=True)
class PlanAgent:
    key: str
    label: str
    prompt: str
    options: AgentOptions
    phase: str = ""
    #: Sonucun `{sonuc.ID}` altında saklanacağı kimlik (yoksa boş).
    result_id: str = ""


@dataclass(frozen=True, slots=True)
class PlanGroup:
    children: tuple[PlanNode, ...]
    parallel: bool
    result_id: str = ""
    #: `her` açılımında öğe adları (çıktı birleşiminde başlık olur).
    item_labels: tuple[str, ...] = ()


PlanNode = PlanAgent | PlanGroup

BoundInputs = Mapping[str, str | tuple[str, ...]]


def bind_inputs(
    spec: WorkflowSpec, given: Mapping[str, object] | None
) -> dict[str, str | tuple[str, ...]]:
    """Varsayılanlar + çağıranın verdiği değerler; tanımda olmayan girdi reddedilir."""
    bound: dict[str, str | tuple[str, ...]] = {item.name: item.default for item in spec.inputs}
    for key, value in (given or {}).items():
        if key not in bound:
            known = ", ".join(sorted(bound)) or "yok"
            raise WorkflowError(f"Bilinmeyen girdi '{key}' (tanımlı girdiler: {known}).")
        bound[key] = coerce_input(value, key)
    return bound


class _Keys:
    """Düğüm anahtarları: kullanıcı `id`si aynen, otomatikler (`a<N>`) çakışmadan.

    Ölçüldü (31 Ekim): [{id: a2}, {}, {}] → ['a2', 'a2', 'a3']; iki ajan aynı düğüme
    iniyor, pano ve başarısız sayısı eksik çıkıyordu.
    """

    def __init__(self, reserved: set[str]) -> None:
        self._numbers: Iterator[int] = iter(range(1, 1_000_000))
        self._taken = set(reserved)

    def next_number(self) -> int:
        return next(self._numbers)

    def auto(self, prefix: str, number: int) -> str:
        key = candidate = f"{prefix}a{number}"
        suffix = 1
        while key in self._taken:
            suffix += 1
            key = f"{candidate}-{suffix}"
        self._taken.add(key)
        return key


def expand(spec: WorkflowSpec, inputs: BoundInputs) -> PlanGroup:
    """Tanımı somut plana aç: `her` öğeleri çözülür, `{oge}` yerine konur."""
    keys = _Keys(_user_ids(spec.steps))
    children = tuple(_expand(step, inputs, keys, phase="") for step in spec.steps)
    return PlanGroup(children, parallel=False)


def _user_ids(steps: tuple[Step, ...]) -> set[str]:
    found: set[str] = set()
    for step in steps:
        if isinstance(step, GroupStep):
            found |= _user_ids(step.steps)
        elif isinstance(step, AgentStep) and step.id:
            found.add(step.id)
    return found


def _expand(step: Step, inputs: BoundInputs, counter: _Keys, *, phase: str) -> PlanNode:
    if isinstance(step, AgentStep):
        return _agent(step, counter, phase=phase)
    if isinstance(step, GroupStep):
        inner_phase = step.phase or phase
        return PlanGroup(
            tuple(_expand(child, inputs, counter, phase=inner_phase) for child in step.steps),
            parallel=step.parallel,
        )
    return _each(step, inputs, counter, phase=phase)


def _agent(
    step: AgentStep,
    counter: _Keys,
    *,
    phase: str,
    item: tuple[int, str] | None = None,
    key_prefix: str = "",
) -> PlanAgent:
    number = counter.next_number()
    prompt = step.prompt
    if item is not None:
        prompt = prompt.replace("{oge_no}", str(item[0])).replace("{oge}", item[1])
    key = step.id or counter.auto(key_prefix, number)
    label = step.label or _label(prompt)
    return PlanAgent(key, label, prompt, step.options, phase=phase, result_id=step.id)


def _each(step: EachStep, inputs: BoundInputs, counter: _Keys, *, phase: str) -> PlanGroup:
    items = step.items
    if step.items_input:
        value = inputs.get(step.items_input, ())
        items = (
            value
            if isinstance(value, tuple)
            else tuple(line.strip() for line in str(value).splitlines() if line.strip())
        )
    if len(items) > MAX_ITEMS:
        raise WorkflowError(f"'her' en fazla {MAX_ITEMS} öğe alabilir (gelen {len(items)}).")
    lanes: list[PlanNode] = []
    for index, item in enumerate(items, start=1):
        stages = tuple(
            _agent(
                stage,
                counter,
                phase=phase,
                item=(index, item),
                key_prefix=f"{step.id or 'her'}{index}.",
            )
            for stage in step.stages
        )
        lanes.append(PlanGroup(stages, parallel=False) if len(stages) > 1 else stages[0])
    return PlanGroup(tuple(lanes), parallel=True, result_id=step.id, item_labels=items)


def _label(prompt: str) -> str:
    first = " ".join(prompt.split())
    return first if len(first) <= 60 else first[:59] + "…"


def agents_in(node: PlanNode) -> list[PlanAgent]:
    """Plandaki bütün ajan düğümleri, çalışma sırasıyla."""
    if isinstance(node, PlanAgent):
        return [node]
    return [agent for child in node.children for agent in agents_in(child)]


def render_prompt(
    prompt: str,
    *,
    inputs: BoundInputs,
    results: Mapping[str, str],
    previous: str,
) -> str:
    """Yer tutucuları doldur. Henüz üretilmemiş sonuç açıkça işaretlenir, uydurulmaz."""

    def _value(match: re.Match[str]) -> str:
        token = match.group(1)
        if token == "onceki":
            return _clip(previous)
        if token.startswith("girdi."):
            value = inputs.get(token[6:], "")
            return "\n".join(value) if isinstance(value, tuple) else value
        if token.startswith("sonuc."):
            found = results.get(token[6:])
            return _clip(found) if found is not None else f"[{token[6:]} sonucu henüz yok]"
        return match.group(0)

    return PLACEHOLDER.sub(_value, prompt)


def _clip(text: str) -> str:
    if len(text) <= RESULT_INSERT_CHARS:
        return text
    return text[:RESULT_INSERT_CHARS] + "\n[… kırpıldı]"
