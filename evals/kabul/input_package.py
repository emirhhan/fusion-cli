"""Yalnız açık kaynaklardan gerçek brief byte'larını hazırlayan üretimsiz paketleyici.

Modül kodu çalıştırılmaz; loader/ortam/model okunmaz. Paket hazır briefler içerir,
ancak bilinmeyen eş koşul kanıtları bütün kontrollü koşuları kapalı tutar.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from evals.kabul.run_manifest import PublicSources

DOMAINS = ("html_oyun", "remotion", "site_kopyasi", "animasyon")
MISSING_EVIDENCE = (
    "current_engine_source",
    "reference_engine_source",
    "configuration_equality",
    "authentication_equivalence",
    "cache_initial_state",
    "memory_isolation",
    "dynamic_context_equivalence",
    "source_snapshot",
    "inspection_snapshot",
    "rubric_snapshot",
    "dependency_versions",
    "functional_B_inspectors",
)


@dataclass(frozen=True, slots=True)
class TaskInput:
    brief: bytes
    timeout_s: float


@dataclass(frozen=True, slots=True)
class PackageProof:
    manifest_digest: str
    missing_inputs: tuple[str, ...]


def _assignments(tree: ast.Module) -> dict[str, ast.expr]:
    result: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    result[target.id] = node.value
    return result


def _text(node: ast.expr) -> str:
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        raise ValueError("Brief kaynağı literal metin olmalı; kod çalıştırılmaz.")
    return node.value


def _brief(assignments: dict[str, ast.expr], source_url: str | None) -> bytes:
    task = assignments.get("TASK")
    if isinstance(task, ast.Constant):
        return _text(task).encode("utf-8")
    if not (
        isinstance(task, ast.Call)
        and isinstance(task.func, ast.Attribute)
        and isinstance(task.func.value, ast.Name)
        and task.func.value.id == "TASK_TEMPLATE"
        and task.func.attr == "format"
        and not task.args
        and len(task.keywords) == 1
        and task.keywords[0].arg == "source"
        and isinstance(task.keywords[0].value, ast.Name)
        and task.keywords[0].value.id == "SOURCE_URL"
    ):
        raise ValueError("Brief kaynağı desteklenen literal veya site template'i olmalı.")
    template = _text(assignments["TASK_TEMPLATE"])
    url = source_url if source_url is not None else _text(assignments["SOURCE_URL"])
    return template.format(source=url).encode("utf-8")


def extract_task(source: bytes, *, source_url: str | None = None) -> TaskInput:
    """TASK ve özgün alan bütçesi AST literalinden alınır; import/exec yok."""
    tree = ast.parse(source)
    assignments = _assignments(tree)
    budget = assignments.get("TIMEOUT_S")
    if budget is None:
        candidates = [
            keyword.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Area"
            for keyword in node.keywords
            if keyword.arg == "timeout_s"
        ]
        if len(candidates) != 1:
            raise ValueError("Özgün alan bütçesi tek ve literal olmalı.")
        budget = candidates[0]
    if (
        not isinstance(budget, ast.Constant)
        or isinstance(budget.value, bool)
        or not isinstance(budget.value, (int, float))
        or not math.isfinite(budget.value)
        or budget.value <= 0
    ):
        raise ValueError("Özgün alan bütçesi pozitif sonlu sayı olmalı.")
    brief = _brief(assignments, source_url)
    if not brief.strip():
        raise ValueError("Brief boş olamaz.")
    return TaskInput(brief, float(budget.value))


def _target(output: Path, name: str) -> Path:
    parts = PurePosixPath(name)
    if (
        not name
        or any(part in {"", ".", ".."} for part in name.split("/"))
        or parts.is_absolute()
        or ".." in parts.parts
        or "\\" in name
        or any(part.lower().startswith(".env") for part in parts.parts)
    ):
        raise ValueError("Paket hedef yolu güvenli göreli public yol olmalı.")
    return output.joinpath(*parts.parts)


def _write(output: Path, name: str, payload: bytes) -> dict[str, object]:
    target = _target(output, name)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return {"path": name, "digest": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}


def _prepare_inputs(
    sources: PublicSources,
    briefs: tuple[tuple[str, str, bytes], ...],
    assets: tuple[tuple[str, str], ...],
) -> tuple[list[tuple[str, str, bytes, float]], list[tuple[str, bytes]], list[str]]:
    tasks: list[tuple[str, str, bytes, float]] = []
    files: list[tuple[str, bytes]] = []
    missing: list[str] = []
    seen: set[str] = set()
    for domain, source, transfer in briefs:
        if domain not in DOMAINS or domain in seen or not transfer.strip():
            raise ValueError("Alan tekrarı veya boş nihai B brief'i geçersiz.")
        transfer.decode("utf-8")
        seen.add(domain)
        raw = sources.read(source)
        task = extract_task(raw)
        tasks.extend(
            ((domain, "A", task.brief, task.timeout_s), (domain, "B", transfer, task.timeout_s))
        )
        files.append(("sources/" + source, raw))
    for target, source in assets:
        _target(Path(), target)
        if source not in sources.allowlist:
            raise ValueError("Kaynak public allowlist içinde değil.")
        candidate = sources.root / source
        if not candidate.exists() and not candidate.is_symlink():
            missing.append("asset:" + target)
            continue
        files.append((target, sources.read(source)))
    missing.extend(domain + ":brief" for domain in DOMAINS if domain not in seen)
    return tasks, files, missing


def materialize_package(
    sources: PublicSources,
    output: Path,
    briefs: tuple[tuple[str, str, bytes], ...],
    assets: tuple[tuple[str, str], ...],
) -> PackageProof:
    """Yeni klasöre byte sadık paket yaz; eksik eş koşullar hiçbir koşuyu açmaz."""
    if output.exists():
        raise ValueError("Paket hedefi zaten var; donmuş girdiler üzerine yazılmaz.")
    tasks, files, missing = _prepare_inputs(sources, briefs, assets)
    names = [name for name, _ in files] + [
        f"briefs/{domain}-{variant}.txt" for domain, variant, _, _ in tasks
    ]
    if "manifest.json" in names:
        raise ValueError("manifest.json paket manifesti için ayrılmış hedef adıdır.")
    for name in names:
        _target(output, name)
    if len(names) != len(set(names)):
        raise ValueError("Paket hedef adları tekil olmalı.")
    output.mkdir(parents=True)
    source_records = [_write(output, name, payload) for name, payload in files]
    brief_records: list[dict[str, object]] = []
    for domain, variant, payload, budget in tasks:
        record = _write(output, f"briefs/{domain}-{variant}.txt", payload)
        record.update(area=domain, variant=variant, timeout_s=budget)
        brief_records.append(record)
    missing_inputs = tuple(sorted(set(missing + list(MISSING_EVIDENCE))))
    runs = [
        {
            "run_id": f"{domain}.{suffix}",
            "area": domain,
            "variant": "B" if suffix == "curB" else "A",
            "engine_role": "reference" if suffix == "refA" else "current",
            "runnable": False,
            "missing_inputs": missing_inputs,
        }
        for domain in DOMAINS
        for suffix in ("refA", "curA", "curB")
    ]
    manifest = {
        "schema": "fusion-public-input-package-v1",
        "status": "unverified",
        "original_baseline_provenance": "unknown",
        "explicit_reference_revision": "3fd76ae292bbcbe5c21bc41b73f17c43908a184f",
        "runs": runs,
        "briefs": brief_records,
        "sources": source_records,
        "missing_inputs": missing_inputs,
        "production_started": False,
    }
    encoded = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    _write(output, "manifest.json", encoded)
    return PackageProof(hashlib.sha256(encoded).hexdigest(), missing_inputs)
