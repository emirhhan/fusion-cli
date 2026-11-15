"""Dinamik iş akışı tanımı (P-062): kısıtlı JSON DSL'in ayrıştırılması ve açılması.

Claude Code'da model `agent()`/`parallel()`/`pipeline()`/`phase()` çağıran bir JS betiği
yazar. Fusion çalıştırılabilir kod yerine VERİ kabul eder: model (ya da kullanıcı) aynı
dört yapıyı JSON ile tarif eder, burada doğrulanır ve somut bir plana açılır. Böylece
tanım eval edilmez, ağ/dosya erişimi yoktur; tek yan etki alt ajanlardır.

    {"ad": "inceleme", "girdiler": {"dosyalar": ["a.py", "b.py"]},
     "adimlar": [
       {"evre": "Keşif", "adimlar": [
         {"her": "{girdi.dosyalar}", "id": "bulgu", "salt_okunur": true,
          "ajan": "{oge} dosyasındaki hataları bul"}]},
       {"ajan": "Bulguları önceliklendir:\\n{sonuc.bulgu}", "id": "rapor"}]}

Düğümler: `ajan` (tek alt ajan), `paralel` (eşzamanlı), `sira` (boru hattı; her adım
`{onceki}` ile bir öncekinin çıktısını alır), `evre` (adlı aşama), `her` (listedeki her
öğe için `ajan` ya da `asamalar` boru hattı, öğeler paralel). Yer tutucular yalnız
`{girdi.X}`, `{sonuc.ID}`, `{onceki}`, `{oge}`, `{oge_no}`; başka süslü parantez metne
dokunulmadan kalır (istemdeki kod örnekleri bozulmasın). İngilizce anahtarlar
(`agent`, `parallel`, `pipeline`, `phase`, `each`, `steps`…) eş anlamlı kabul edilir.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ...core.errors import FusionError

#: Tanımdaki en fazla düğüm (açılmadan önce) ve iç içelik.
MAX_STEPS = 200
MAX_NESTING = 6
#: Tek bir ajan isteminin en fazla karakteri (yer tutucular doldurulmadan).
MAX_PROMPT_CHARS = 8_000
#: `her` düğümünün en fazla öğesi (Claude Code `parallel()` 4.096; burada ajan bütçesi
#: zaten daha önce dolar, liste yalnız açılışı sınırlar).
MAX_ITEMS = 256
#: Ad: kayıt dosyası adı da olur.
NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")
_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
PLACEHOLDER = re.compile(r"\{(girdi\.[A-Za-z0-9_]+|sonuc\.[A-Za-z0-9_-]+|onceki|oge|oge_no)\}")

_ALIASES: dict[str, str] = {
    "agent": "ajan",
    "parallel": "paralel",
    "pipeline": "sira",
    "sequence": "sira",
    "phase": "evre",
    "each": "her",
    "steps": "adimlar",
    "stages": "asamalar",
    "name": "ad",
    "description": "aciklama",
    "args": "girdiler",
    "inputs": "girdiler",
    "max_agents": "en_fazla_ajan",
    "concurrency": "eszamanli",
    "label": "baslik",
    "persona": "uzman",
    "read_only": "salt_okunur",
    "write_scope": "yazma_alani",
    "isolation": "izolasyon",
}
_KINDS = ("ajan", "paralel", "sira", "evre", "her")


class WorkflowError(FusionError):
    """İş akışı tanımı geçersiz ya da çalıştırılamıyor (mesaj modele/kullanıcıya gider)."""


@dataclass(frozen=True, slots=True)
class AgentOptions:
    persona: str = ""
    read_only: bool = False
    write_scope: tuple[str, ...] = ()
    isolation: str = ""


@dataclass(frozen=True, slots=True)
class AgentStep:
    prompt: str
    id: str = ""
    label: str = ""
    options: AgentOptions = AgentOptions()


@dataclass(frozen=True, slots=True)
class GroupStep:
    """`paralel`, `sira` ve `evre` düğümleri (evrenin adı `phase`)."""

    steps: tuple[Step, ...]
    parallel: bool
    phase: str = ""


@dataclass(frozen=True, slots=True)
class EachStep:
    #: Düz liste ya da `{girdi.X}` başvurusu (açılırken çözülür).
    items: tuple[str, ...]
    items_input: str
    stages: tuple[AgentStep, ...]
    id: str = ""


Step = AgentStep | GroupStep | EachStep


@dataclass(frozen=True, slots=True)
class WorkflowInput:
    name: str
    default: str | tuple[str, ...] = ""


@dataclass(frozen=True, slots=True)
class WorkflowSpec:
    name: str
    description: str
    inputs: tuple[WorkflowInput, ...]
    steps: tuple[Step, ...]
    max_agents: int = 0
    concurrency: int = 0
    #: Kaydedilecek ham tanım (normalize JSON).
    source: str = ""


# --------------------------------------------------------------------------- #
# Ayrıştırma
# --------------------------------------------------------------------------- #


def parse_workflow(raw: object, *, fallback_name: str = "akis") -> WorkflowSpec:
    """Ham tanımı (sözlük, JSON metni ya da adım listesi) doğrula ve tanıma çevir."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as error:
            raise WorkflowError(
                f"Tanım geçerli JSON değil: {error.msg} (satır {error.lineno})."
            ) from error
    if isinstance(raw, list):
        raw = {"adimlar": raw}
    if not isinstance(raw, Mapping):
        raise WorkflowError("Tanım bir nesne ya da adım listesi olmalı.")
    top = _normalized(raw)
    name = str(top.get("ad") or fallback_name).strip().casefold()
    if not NAME_PATTERN.match(name):
        raise WorkflowError("'ad' küçük harf, rakam, '-' ya da '_' olmalı (en fazla 48).")
    counter = _Counter()
    steps = _steps(top.get("adimlar"), counter, depth=1, where="adimlar")
    if not steps:
        raise WorkflowError("'adimlar' en az bir adım içermeli.")
    spec = WorkflowSpec(
        name=name,
        description=str(top.get("aciklama") or "").strip(),
        inputs=_inputs(top.get("girdiler")),
        steps=steps,
        max_agents=_positive(top.get("en_fazla_ajan"), "en_fazla_ajan"),
        concurrency=_positive(top.get("eszamanli"), "eszamanli"),
        source=json.dumps(_plain_source(raw, name), ensure_ascii=False, indent=2),
    )
    _check_references(spec)
    return spec


@dataclass(slots=True)
class _Counter:
    steps: int = 0
    ids: set[str] | None = None

    def bump(self, where: str) -> None:
        self.steps += 1
        if self.steps > MAX_STEPS:
            raise WorkflowError(f"Tanım en fazla {MAX_STEPS} adım içerebilir ({where}).")

    def claim(self, identifier: str, where: str) -> None:
        if self.ids is None:
            self.ids = set()
        if not _ID_PATTERN.match(identifier):
            raise WorkflowError(f"{where}: 'id' harf, rakam, '-' ya da '_' olmalı.")
        if identifier in self.ids:
            raise WorkflowError(f"{where}: '{identifier}' kimliği iki kez kullanılmış.")
        self.ids.add(identifier)


def _normalized(raw: Mapping[object, object]) -> dict[str, object]:
    return {_ALIASES.get(str(key), str(key)): value for key, value in raw.items()}


def _plain_source(raw: Mapping[object, object], name: str) -> object:
    return {**{str(key): value for key, value in raw.items()}, "ad": name}


def _steps(raw: object, counter: _Counter, *, depth: int, where: str) -> tuple[Step, ...]:
    if depth > MAX_NESTING:
        raise WorkflowError(f"{where}: iç içelik en fazla {MAX_NESTING} kat olabilir.")
    if not isinstance(raw, list):
        raise WorkflowError(f"{where}: adım listesi olmalı.")
    return tuple(
        _step(item, counter, depth=depth, where=f"{where}[{index}]")
        for index, item in enumerate(raw)
    )


def _step(raw: object, counter: _Counter, *, depth: int, where: str) -> Step:
    counter.bump(where)
    if isinstance(raw, str):
        return _agent({"ajan": raw}, counter, where)
    if not isinstance(raw, Mapping):
        raise WorkflowError(f"{where}: adım nesne ya da istem metni olmalı.")
    node = _normalized(raw)
    kinds = [kind for kind in _KINDS if kind in node]
    if "her" in kinds:
        return _each(node, counter, depth=depth, where=where)
    if len(kinds) != 1:
        raise WorkflowError(f"{where}: tam olarak biri olmalı: ajan, paralel, sira, evre, her.")
    kind = kinds[0]
    if kind == "ajan":
        return _agent(node, counter, where)
    if kind == "evre":
        phase = str(node.get("evre") or "").strip()
        if not phase:
            raise WorkflowError(f"{where}: 'evre' adı boş olamaz.")
        inner = _steps(node.get("adimlar"), counter, depth=depth + 1, where=f"{where}.adimlar")
        return GroupStep(inner, parallel=False, phase=phase[:80])
    inner = _steps(node.get(kind), counter, depth=depth + 1, where=f"{where}.{kind}")
    return GroupStep(inner, parallel=kind == "paralel")


def _agent(node: Mapping[str, object], counter: _Counter, where: str) -> AgentStep:
    prompt = node.get("ajan")
    if not isinstance(prompt, str) or not prompt.strip():
        raise WorkflowError(f"{where}: 'ajan' boş olmayan bir istem metni olmalı.")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise WorkflowError(f"{where}: istem en fazla {MAX_PROMPT_CHARS} karakter olabilir.")
    identifier = str(node.get("id") or "").strip()
    if identifier:
        counter.claim(identifier, where)
    return AgentStep(
        prompt=prompt.strip(),
        id=identifier,
        label=str(node.get("baslik") or "").strip()[:80],
        options=_options(node, where),
    )


def _each(node: Mapping[str, object], counter: _Counter, *, depth: int, where: str) -> EachStep:
    raw_items = node.get("her")
    items: tuple[str, ...] = ()
    items_input = ""
    if isinstance(raw_items, str):
        match = re.fullmatch(r"\{girdi\.([A-Za-z0-9_]+)\}", raw_items.strip())
        if match is None:
            raise WorkflowError(f"{where}: 'her' bir liste ya da '{{girdi.ad}}' olmalı.")
        items_input = match.group(1)
    elif isinstance(raw_items, list) and all(isinstance(item, str) for item in raw_items):
        items = _checked_items(tuple(item for item in raw_items if item.strip()), where)
    else:
        raise WorkflowError(f"{where}: 'her' metin listesi olmalı.")
    stages_raw = node.get("asamalar")
    if stages_raw is None:
        stages_raw = [{key: value for key, value in node.items() if key not in {"her", "id"}}]
    if not isinstance(stages_raw, list) or not stages_raw:
        raise WorkflowError(f"{where}: 'her' için 'ajan' ya da 'asamalar' gerekli.")
    shared = {
        key: node[key]
        for key in ("uzman", "salt_okunur", "yazma_alani", "izolasyon")
        if key in node
    }
    stages: list[AgentStep] = []
    for index, stage in enumerate(stages_raw):
        stage_node = {"ajan": stage} if isinstance(stage, str) else stage
        if not isinstance(stage_node, Mapping):
            raise WorkflowError(
                f"{where}.asamalar[{index}]: istem metni ya da ajan nesnesi olmalı."
            )
        merged = {**shared, **_normalized(stage_node)}
        merged.pop("id", None)
        stages.append(_agent(merged, counter, f"{where}.asamalar[{index}]"))
    identifier = str(node.get("id") or "").strip()
    if identifier:
        counter.claim(identifier, where)
    return EachStep(items=items, items_input=items_input, stages=tuple(stages), id=identifier)


def _checked_items(items: tuple[str, ...], where: str) -> tuple[str, ...]:
    if len(items) > MAX_ITEMS:
        raise WorkflowError(f"{where}: 'her' en fazla {MAX_ITEMS} öğe alabilir.")
    return items


_FALSE_WORDS = frozenset({"false", "no", "hayır", "hayir", "0", "off", ""})


def _options(node: Mapping[str, object], where: str) -> AgentOptions:
    scope = node.get("yazma_alani", ())
    if not isinstance(scope, (list, tuple)) or not all(isinstance(item, str) for item in scope):
        raise WorkflowError(f"{where}: 'yazma_alani' metin listesi olmalı.")
    isolation = str(node.get("izolasyon") or "")
    if isolation not in {"", "worktree"}:
        raise WorkflowError(f"{where}: 'izolasyon' yalnız 'worktree' olabilir.")
    read_only = node.get("salt_okunur", False)
    # Açık-güvenli: belirsiz değer salt-okuma sayılır (`team._parse_read_only` ile aynı).
    if isinstance(read_only, str):
        read_only = read_only.strip().casefold() not in _FALSE_WORDS
    return AgentOptions(
        persona=str(node.get("uzman") or "").strip(),
        read_only=bool(read_only),
        write_scope=tuple(item.strip() for item in scope if item.strip()),
        isolation=isolation,
    )


def _inputs(raw: object) -> tuple[WorkflowInput, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, Mapping):
        raise WorkflowError("'girdiler' ad → varsayılan değer nesnesi olmalı.")
    inputs: list[WorkflowInput] = []
    for key, value in raw.items():
        name = str(key)
        if not re.fullmatch(r"[A-Za-z0-9_]+", name):
            raise WorkflowError(f"girdiler: '{name}' adı harf, rakam ya da '_' olmalı.")
        inputs.append(WorkflowInput(name, coerce_input(value, name)))
    return tuple(inputs)


def coerce_input(value: object, name: str) -> str | tuple[str, ...]:
    """Girdi değeri metin ya da metin listesi olur; sayı/mantıksal metne çevrilir."""
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    raise WorkflowError(f"girdiler.{name}: metin ya da metin listesi olmalı.")


def _positive(value: object, name: str) -> int:
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise WorkflowError(f"'{name}' pozitif tam sayı olmalı.")
    return value


def _walk(steps: Sequence[Step]) -> list[AgentStep | EachStep]:
    found: list[AgentStep | EachStep] = []
    for step in steps:
        if isinstance(step, GroupStep):
            found.extend(_walk(step.steps))
        else:
            found.append(step)
    return found


def _check_references(spec: WorkflowSpec) -> None:
    ids = {step.id for step in _walk(spec.steps) if step.id}
    inputs = {item.name for item in spec.inputs}
    for step in _walk(spec.steps):
        prompts = [step.prompt] if isinstance(step, AgentStep) else [s.prompt for s in step.stages]
        for prompt in prompts:
            for token in PLACEHOLDER.findall(prompt):
                if token.startswith("sonuc.") and token[6:] not in ids:
                    raise WorkflowError(f"'{{{token}}}': bu kimlikte adım yok.")
                if token.startswith("girdi.") and token[6:] not in inputs:
                    raise WorkflowError(f"'{{{token}}}': 'girdiler' içinde tanımlı değil.")
                if token in {"oge", "oge_no"} and isinstance(step, AgentStep):
                    raise WorkflowError(f"'{{{token}}}' yalnız 'her' adımında kullanılabilir.")
        if isinstance(step, EachStep) and step.items_input and step.items_input not in inputs:
            raise WorkflowError(f"'her': '{{girdi.{step.items_input}}}' tanımlı değil.")
