"""Sıralı still taşıması: kaynak manifesti ve runtime kaydı; tam video kanıtı değil."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import tempfile
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from ..config.paths import bundled_skills_dir
from ..core.constants import MAX_CHECKPOINT_OUTPUT_CHARS
from ..core.repair_ledger import SourceFingerprint
from .job_evidence import prepare_manifest


@dataclass(frozen=True, slots=True)
class RenderRequest:
    root: Path
    entry: str
    composition: str
    frame: int
    artifact: str
    sources: tuple[str, ...]
    timeout_s: float


@dataclass(frozen=True, slots=True)
class ProcessOutput:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    framed_count: int | None = None


@dataclass(frozen=True, slots=True)
class RuntimeRecord:
    session: str
    composition: str
    frame: int
    active_scenes: tuple[str, ...]
    feature_ready: bool
    audit_settled: bool
    findings: tuple[str, ...]
    runtime_executed: bool
    timeline_seen: bool
    active_scene_kinds: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RenderedFrame:
    session_id: str
    rendered: bool
    runtime: RuntimeRecord | None
    source_before: tuple[SourceFingerprint, ...]
    source_after: tuple[SourceFingerprint, ...]
    error: str = ""


Runner = Callable[[tuple[str, ...], Path, float], Awaitable[ProcessOutput]]


async def _run(command: tuple[str, ...], root: Path, deadline_s: float) -> ProcessOutput:
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=root,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    assert process.stdout is not None and process.stderr is not None
    readers = [
        asyncio.create_task(_read_bounded(stream)) for stream in (process.stdout, process.stderr)
    ]
    timed_out = False
    try:
        await asyncio.wait_for(process.wait(), deadline_s)
    except TimeoutError:
        timed_out = True
    finally:
        try:
            await _terminate_owned_group(process, deadline_s, command)
        finally:
            stdout, stderr = await asyncio.gather(*readers)
    return ProcessOutput(
        process.returncode or 0, stdout.text, stderr.text, timed_out, stdout.framed_count
    )


@dataclass(frozen=True, slots=True)
class StreamOutput:
    text: str
    framed_count: int


async def _read_bounded(stream: asyncio.StreamReader) -> StreamOutput:
    tail, overlap = b"", b"\n"
    prefix = b"\nFUSION_OBSERVE_V1:"
    framed_count = 0
    while chunk := await stream.read(MAX_CHECKPOINT_OUTPUT_CHARS):
        combined = overlap + chunk
        framed_count += combined.count(prefix)
        overlap = combined[-(len(prefix) - 1) :]
        tail = (tail + chunk)[-MAX_CHECKPOINT_OUTPUT_CHARS:]
    return StreamOutput(tail.decode(errors="replace")[:MAX_CHECKPOINT_OUTPUT_CHARS], framed_count)


def _signal_owned_group(pid: int, sig: signal.Signals) -> None:
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        return  # Bizim süreç grubumuz zaten kapanmış; başka PID aranmaz.


async def _terminate_owned_group(
    process: asyncio.subprocess.Process, grace_s: float, command: tuple[str, ...]
) -> None:
    """Yalnız start_new_session ile bize ait grubun dirençli çocuklarını kapat."""
    for pid in {process.pid, *_detached_groups(command)}:
        _signal_owned_group(pid, signal.SIGTERM)
    try:
        await asyncio.wait_for(process.wait(), min(grace_s, 1.0))
    except TimeoutError:
        pass  # Süreli nazik kapanış bitti; finally aynı gruba KILL gönderir.
    finally:
        # Lider kapanmış olsa da açık pipe/Chromium/esbuild çocukları kalabilir.
        # Tekrar iptal de bu senkron sinyali atlayamaz.
        for pid in {process.pid, *_detached_groups(command)}:
            _signal_owned_group(pid, signal.SIGKILL)
        await process.wait()


def _detached_groups(command: tuple[str, ...]) -> tuple[int, ...]:
    if len(command) != 3 or Path(command[1]).name != "observe.cjs":
        return ()
    try:
        payload = json.loads(command[2])
        if not isinstance(payload, dict):
            return ()
        path = payload.get("cleanupFile")
        if not isinstance(path, str):
            return ()
        return tuple(
            int(line)
            for line in Path(path).read_text().splitlines()
            if line.isdecimal() and int(line) > 0
        )
    except (OSError, ValueError, TypeError):
        return ()


def _manifest(request: RenderRequest) -> tuple[SourceFingerprint, ...]:
    manifest = prepare_manifest(
        {"failure_check": "remotion_runtime", "failure_sources": list(request.sources)},
        request.root,
    )
    if manifest is None:
        raise ValueError("Runtime kaydı için kaynak manifesti gerekli.")
    return manifest.sources


def _local_path(root: Path, value: str) -> Path:
    original = root / value
    resolved = original.resolve()
    if any(part.startswith(".env") for path in (original, resolved) for part in path.parts):
        raise ValueError("Runtime taşıması sır yolunu kullanamaz.")
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("Runtime taşımasının yolları proje içinde olmalı.")
    return resolved


async def observe_frame(
    request: RenderRequest,
    *,
    runner: Runner = _run,
    new_session: Callable[[], str] = lambda: uuid.uuid4().hex,
) -> RenderedFrame:
    session = new_session()
    if not session or type(request.frame) is not int or request.frame < 0 or request.timeout_s <= 0:
        raise ValueError("Runtime oturumu, kare ve süre geçerli olmalı.")
    entry = _local_path(request.root, request.entry)
    artifact = _local_path(request.root, request.artifact)
    if artifact.exists():
        raise ValueError("Kare artefaktı zaten var; yeni oturum için yeni çıktı yolu seç.")
    before = await asyncio.to_thread(_manifest, request)
    try:
        with tempfile.TemporaryDirectory(prefix="fusion-remotion-") as directory:
            payload = _payload(request, entry, artifact, session, Path(directory) / "owned-groups")
            script = bundled_skills_dir() / "remotion-video/kit/observe.cjs"
            process = await runner(("node", str(script), payload), request.root, request.timeout_s)
    except (OSError, TimeoutError) as error:
        after = await asyncio.to_thread(_manifest, request)
        return RenderedFrame(session, False, None, before, after, type(error).__name__)
    after = await asyncio.to_thread(_manifest, request)
    if process.timed_out:
        detail = _progress_detail(process.stderr, session, request)
        return RenderedFrame(
            session,
            False,
            None,
            before,
            after,
            ("Toplam gözlem süresi doldu. " + detail)[:MAX_CHECKPOINT_OUTPUT_CHARS],
        )
    response = (
        ObservationResponse(None, False, "Gözlem protokolü birden fazla sonuç içeriyor.")
        if process.framed_count is not None and process.framed_count > 1
        else _response(process.stdout, session, request)
    )
    record = response.runtime
    rendered = process.exit_code == 0 and response.rendered
    rendered = rendered and artifact.is_file() and _is_png(artifact)
    detail = (
        "" if rendered and record else response.error or "Gerçek still/runtime kaydı doğrulanamadı."
    )
    return RenderedFrame(session, rendered, record, before, after, detail)


def _progress_detail(stderr: str, session: str, request: RenderRequest) -> str:
    prefix = "FUSION_PROGRESS_V1:"
    details = []
    for line in stderr.splitlines():
        if not line.startswith(prefix):
            continue
        try:
            value = json.loads(line[len(prefix) :])
        except ValueError:
            continue
        if not isinstance(value, dict) or (
            value.get("session") != session
            or value.get("composition") != request.composition
            or value.get("frame") != request.frame
        ):
            continue
        stage, message = value.get("stage"), value.get("message", "")
        if isinstance(stage, str) and isinstance(message, str):
            details.append(f"{stage}: {message}")
    return "\n".join(details)[-MAX_CHECKPOINT_OUTPUT_CHARS:]


@dataclass(frozen=True, slots=True)
class ObservationResponse:
    runtime: RuntimeRecord | None
    rendered: bool
    error: str = ""


def _response(stdout: str, session: str, request: RenderRequest) -> ObservationResponse:
    prefix = "FUSION_OBSERVE_V1:"
    frames = [line[len(prefix) :] for line in stdout.splitlines() if line.startswith(prefix)]
    try:
        if len(frames) > 1:
            raise ValueError("Tek gözlem cevabı gerekli")
        # Eski enjekte runner yalnız bütün çıktısı tek JSON ise uyumludur.
        value = json.loads(frames[0] if frames else stdout)
        if not isinstance(value, dict) or (frames and value.get("session") != session):
            raise ValueError("Oturum eşleşmedi")
        if frames and (
            value.get("composition") != request.composition or value.get("frame") != request.frame
        ):
            raise ValueError("Composition/kare eşleşmedi")
        runtime = _record(value.get("record"))
        error, stage = value.get("error", ""), value.get("stage", "")
        if not isinstance(error, str) or not isinstance(stage, str):
            raise ValueError("Hata alanları metin olmalı")
        detail = f"{stage}: {error}" if error and stage else error
        return ObservationResponse(
            runtime, value.get("rendered") is True, detail[:MAX_CHECKPOINT_OUTPUT_CHARS]
        )
    except (ValueError, TypeError):
        return ObservationResponse(
            None, False, "Gözlem protokol cevabı tek ve geçerli oturum kaydı değil."
        )


def _record(value: object) -> RuntimeRecord | None:
    if not isinstance(value, dict):
        return None
    texts = [value.get(name) for name in ("session", "composition")]
    flags = [
        value.get(name)
        for name in ("featureReady", "auditSettled", "runtimeExecuted", "timelineSeen")
    ]
    scenes, findings, frame = value.get("activeScenes"), value.get("findings"), value.get("frame")
    if not all(isinstance(text, str) and text for text in texts) or type(frame) is not int:
        return None
    if not all(type(flag) is bool for flag in flags):
        return None
    if not isinstance(scenes, list) or not isinstance(findings, list):
        return None
    if not all(isinstance(item, str) for item in (*scenes, *findings)):
        return None
    kinds = value.get("activeSceneKinds", [])
    if not isinstance(kinds, list) or not all(isinstance(kind, str) for kind in kinds):
        return None
    return RuntimeRecord(
        str(texts[0]),
        str(texts[1]),
        frame,
        tuple(scenes),
        bool(flags[0]),
        bool(flags[1]),
        tuple(findings),
        bool(flags[2]),
        bool(flags[3]),
        tuple(kinds),
    )


def _is_png(path: Path) -> bool:
    with path.open("rb") as stream:
        return stream.read(8) == b"\x89PNG\r\n\x1a\n"


def _payload(
    request: RenderRequest, entry: Path, artifact: Path, session: str, cleanup: Path
) -> str:
    return json.dumps(
        {
            "entry": str(entry),
            "composition": request.composition,
            "frame": request.frame,
            "artifact": str(artifact),
            "session": session,
            "timeoutMs": int(request.timeout_s * 1000),
            "cleanupFile": str(cleanup),
            "diagnosticLimit": MAX_CHECKPOINT_OUTPUT_CHARS,
        }
    )
