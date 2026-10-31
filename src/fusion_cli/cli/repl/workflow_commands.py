"""`/workflows` komutu (P-062): kayıtlı iş akışları, koşular, iptal ve çalıştırma.

    /workflows                    kayıtlı tanımlar + son koşular
    /workflows goster <ad|kosu>   tanımın JSON'u ya da koşunun düğümleri
    /workflows iptal <kosu>       koşan iş akışına iptal işareti bırak
    /workflows sil <ad>           kayıtlı tanımı sil
    /workflows <ad> [k=v ...]     kayıtlı akışı ajana çalıştırt (girdilerle)

Çalıştırma bir ajan turu hazırlar (`pending_task`); masaüstü aynı komutu `run_command`
ile çalıştırır ve hazırlanan turu gönderir. Metin Rich işaretlemesi taşımaz (köşeli
parantez yok): REPL sonucu işaretlemeli basar.
"""

from __future__ import annotations

import datetime
import json
import shlex

from ...engines.agent.workflow_spec import WorkflowError
from ...engines.agent.workflow_store import RunRecord, WorkflowStore
from ...engines.agent.workflow_tools import workflow_store
from .state import Engine, ReplState

#: Listede gösterilecek son koşu sayısı.
RECENT_RUNS = 8

USAGE = (
    "Kullanım: /workflows [goster <ad|koşu>] | iptal <koşu> | sil <ad> | <ad> [girdi=değer …]\n"
    "Tanımlar: .fusion/workflows/<ad>.json (proje), <yapılandırma>/workflows/ (kullanıcı)."
)
NONE_SAVED = "Kayıtlı iş akışı yok. Ajandan 'workflow_run ... kaydet: true' ile kaydetmesini iste."
RUN_TASK = (
    "Kayıtlı '{name}' iş akışını workflow_run aracıyla çalıştır (ad: \"{name}\"{inputs}). "
    "Bittiğinde sonucu ve yarım kalan adımları kısaca özetle."
)


def workflows_command(state: ReplState, argument: str) -> str:
    store = workflow_store(state.root)
    try:
        words = shlex.split(argument)
    except ValueError:
        return USAGE
    if not words or words[0] in {"liste", "list"}:
        return overview(store)
    action, rest = words[0].casefold(), words[1:]
    if action in {"goster", "göster", "show"}:
        return show(store, rest[0]) if rest else USAGE
    if action in {"iptal", "cancel", "stop"}:
        if not rest:
            return USAGE
        if store.request_cancel(rest[0]):
            return f"İptal işareti bırakıldı: {rest[0]}. Koşan ajanlar yarım saniye içinde durur."
        return f"Koşan bir '{rest[0]}' koşusu yok."
    if action in {"sil", "delete"}:
        if not rest:
            return USAGE
        removed = store.delete(rest[0])
        return f"Silindi: {removed}" if removed else f"'{rest[0]}' adlı kayıtlı iş akışı yok."
    return _prepare_run(state, store, words)


def _prepare_run(state: ReplState, store: WorkflowStore, words: list[str]) -> str:
    name, pairs = words[0], words[1:]
    if store.find(name) is None:
        return f"'{name}' adlı kayıtlı iş akışı yok.\n\n{overview(store)}"
    inputs: dict[str, str] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            return f"Girdi 'ad=değer' biçiminde olmalı: {pair}"
        inputs[key] = value
    rendered = f", girdiler: {json.dumps(inputs, ensure_ascii=False)}" if inputs else ""
    state.engine = Engine.AGENT
    state.pending_task = RUN_TASK.format(name=name, inputs=rendered)
    return f"'{name}' iş akışı ajana veriliyor…"


def overview(store: WorkflowStore) -> str:
    saved = store.definitions()
    lines = ["Kayıtlı iş akışları:"] if saved else [NONE_SAVED]
    lines.extend(
        f"  {item.name}  ({item.scope}){'  — ' + item.description if item.description else ''}"
        for item in saved
    )
    runs = store.runs(RECENT_RUNS)
    if runs:
        lines.extend(("", "Son koşular:"))
        lines.extend(f"  {run_line(run)}" for run in runs)
    return "\n".join(lines)


def run_line(run: RunRecord) -> str:
    done = sum(node.status == "tamam" for node in run.nodes)
    when = datetime.datetime.fromtimestamp(run.started_at).strftime("%d.%m %H:%M")
    phase = f" · evre: {run.phase}" if run.phase and run.status == "calisiyor" else ""
    return (
        f"{run.run_id}  {run.name}  {run.status}  {done}/{len(run.nodes)} adım · "
        f"{run.agents_started} ajan · {when}{phase}"
    )


def show(store: WorkflowStore, target: str) -> str:
    run = store.run(target)
    if run is not None:
        lines = [run_line(run)]
        if run.message:
            lines.append(f"  {run.message}")
        lines.extend(
            f"  {node.status:<10} {node.id}: {node.label}"
            + (f" — {node.summary}" if node.summary else "")
            for node in run.nodes
        )
        if run.report:
            lines.extend(("", run.report))
        return "\n".join(lines)
    try:
        spec = store.load(target)
    except WorkflowError as error:
        return str(error)
    return spec.source
