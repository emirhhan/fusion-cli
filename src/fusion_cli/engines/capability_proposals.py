"""Doğrulanmış plan önerilerini mevcut beceri kütüphanesine açıkça aktarır."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
from dataclasses import asdict
from pathlib import Path

from ..config.paths import capabilities_dir, memory_dir
from ..core.checkpoint import CheckpointStore
from ..core.evidence import EvidenceStatus
from ..core.execution_plan import ExecutionPlan, PlanStatus, StepStatus, VerificationCheckKind
from ..core.memory import SkillProposal, SkillProposalMemory
from ..core.proposal_invocation import ProposalInvocation, body_revision, metadata_line
from ..core.redaction import contains_sensitive, redact
from ..memory.checkpoint_store import JsonCheckpointStore
from ..memory.skill_proposals import SkillProposalError, SkillProposalStore
from ..tools.capabilities import CapabilityRegistry
from ..tools.emulation import validate_arguments
from ..tools.proposal_policy import is_supported_schema
from .agent.step_verification import evaluate_file_check
from .routine_source import routine_spec

PROPOSAL_FILENAME = "skill-proposals.json"
NO_PROPOSALS = "Doğrulanmış beceri önerisi yok."
PROPOSAL_NOT_FOUND = "Öneri bulunamadı; kimliği ve seçilen split değerini kontrol et."
UNSUPPORTED_SOURCE = (
    "Rutin kaynağı doğrulanamadı; aynı çalışma alanındaki tamamlanmış planı kontrol et."
)
UNSUPPORTED_CONDITION = "Önkoşul desteklenmiyor; kayıtlı planın benzersiz dosya kontrolü gerekli."
INVALID_PARAMETERS = "Rutin parametreleri geçersiz; önerinin girdi şemasını kontrol et."
UNSAFE_CONTENT = "Hassas bilgi veya dinamik şablon içeren öneri kurulamaz."
INVALID_NAME = "Rutin adı güvenli bir beceri klasörü adı olmalı."
EXISTING_SKILL = "Beceri veya hedef zaten var; mevcut içerik değiştirilmedi."
WRITE_FAILED = "Beceri yazılamadı; hedefteki bağları ve dizin izinlerini kontrol et."
PRECONDITION_FAILED = "Önkoşul güncel çalışma alanında doğrulanamadı; kaynak dosyaları kontrol et."
APPLIED = "Beceri kuruldu: {name}. Mevcut beceri keşfi ve /{name} çağrısı kullanılabilir."
_NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,79}\Z")
_FILE_KINDS = frozenset({VerificationCheckKind.FILE_EXISTS, VerificationCheckKind.FILE_CONTAINS})
_SKILL_FILENAME = "SKILL.md"
_PENDING_FILENAME = ".skill-pending"


def proposal_store_path() -> Path:
    """CLI ve runtime gözlemcisi için yapılandırılmış bellek altındaki tek yol."""
    return memory_dir() / PROPOSAL_FILENAME


def proposal_service(home: Path, root: Path) -> CapabilityProposals:
    """Mevcut veri kökleri ve adaptörlerle kullanıcı komutunu bağla."""
    return CapabilityProposals(
        SkillProposalStore(proposal_store_path()),
        JsonCheckpointStore(memory_dir() / "workflow-checkpoints"),
        root=root,
        installed=capabilities_dir(),
        library=CapabilityRegistry(home, root),
    )


class CapabilityProposals:
    """Öneri görünürlüğü ve açık kurulumun motor sınırı."""

    def __init__(
        self,
        store: SkillProposalMemory,
        checkpoints: CheckpointStore,
        *,
        root: Path,
        installed: Path,
        library: CapabilityRegistry,
    ) -> None:
        self._store = store
        self._checkpoints = checkpoints
        self._root = root
        self._installed = installed
        self._library = library

    async def list(self, *, source_split: str | None = None) -> str:
        """Eşik üstündeki önerileri göster; kurulum yan etkisi üretme."""
        proposals = await self._store.list(source_split=source_split)
        return (
            redact(
                "\n".join(
                    f"{item.id}  {item.routine.routine_id}  {item.routine.description}"
                    for item in proposals
                )
            )
            or NO_PROPOSALS
        )

    async def show(self, proposal_id: str, *, source_split: str | None = None) -> str:
        """Şemayı, önkoşulları ve geçmiş kanıt referanslarını açıkça göster."""
        proposal = await self._select(proposal_id, source_split)
        return redact(
            json.dumps(
                _redacted(_proposal_payload(proposal)), ensure_ascii=False, indent=2, default=str
            )
        )

    async def apply(
        self,
        proposal_id: str,
        parameters: str,
        *,
        source_split: str | None = None,
    ) -> str:
        """Yalnız açık komutta şemayı ve güncel dosya önkoşullarını ölçerek kur."""
        proposal = await self._select(proposal_id, source_split)
        arguments = _parameters(proposal, parameters)
        name = proposal.routine.routine_id
        if _NAME.fullmatch(name) is None:
            raise SkillProposalError(INVALID_NAME)
        plan = await asyncio.to_thread(self._validated_plan, proposal)
        content = _skill_text(proposal, plan, arguments)
        await asyncio.to_thread(self._install, name, content)
        return APPLIED.format(name=name)

    async def _select(self, proposal_id: str, source_split: str | None) -> SkillProposal:
        proposals = await self._store.list(source_split=source_split)
        proposal = next((item for item in proposals if item.id == proposal_id), None)
        if proposal is None:
            raise SkillProposalError(PROPOSAL_NOT_FOUND)
        return proposal

    def _validated_plan(self, proposal: SkillProposal) -> ExecutionPlan:
        routine = proposal.routine
        saved = self._checkpoints.load(routine.routine_id)
        if (
            saved is None
            or Path(saved.root).resolve() != self._root.resolve()
            or saved.plan.plan_id != routine.routine_id
            or saved.plan.task != routine.description
            or saved.plan.status is not PlanStatus.COMPLETED
            or not saved.plan.steps
            or any(step.status is not StepStatus.COMPLETED for step in saved.plan.steps)
        ):
            raise SkillProposalError(UNSUPPORTED_SOURCE)
        if not routine.source_digest or routine_spec(saved.plan, self._root) != routine:
            raise SkillProposalError(UNSUPPORTED_SOURCE)
        checks = tuple(check for step in saved.plan.steps for check in step.verification_checks)
        identities = tuple(check.criterion_id for check in checks)
        references = {*routine.preconditions, *routine.checks}
        if len(set(identities)) != len(identities) or references != set(identities):
            raise SkillProposalError(UNSUPPORTED_CONDITION)
        for check in checks:
            if (
                check.kind not in _FILE_KINDS
                or not check.target
                or (check.kind is VerificationCheckKind.FILE_CONTAINS and not check.expected)
            ):
                raise SkillProposalError(UNSUPPORTED_CONDITION)
            _safe_content(asdict(check))
            if not _is_safe_target(self._root, check.target):
                raise SkillProposalError(UNSUPPORTED_CONDITION)
            if check.criterion_id in routine.preconditions:
                result = evaluate_file_check(check, self._root)
                if not result.applicable or result.status is not EvidenceStatus.PASSED:
                    raise SkillProposalError(PRECONDITION_FAILED)
        return saved.plan

    def _install(self, name: str, content: str) -> None:
        self._library.invalidate()
        if any(item.name == name for item in self._library.skills()):
            raise SkillProposalError(EXISTING_SKILL)
        try:
            _install_exclusive(self._installed, name, content)
        except FileExistsError as error:
            raise SkillProposalError(EXISTING_SKILL) from error
        except OSError as error:
            raise SkillProposalError(WRITE_FAILED) from error


def _is_safe_target(root: Path, target: str) -> bool:
    path = Path(target)
    if path.is_absolute() or ".." in path.parts:
        return False
    current = root
    for component in path.parts:
        current = current / component
        if current.is_symlink():
            return False
    return True


def _parameters(proposal: SkillProposal, raw: str) -> str:
    """Mevcut araç şeması doğrulayıcısını kullan; hata mesajında girdiyi yansıtma."""
    try:
        arguments = json.loads(raw)
        schema = json.loads(proposal.routine.input_schema)
        _safe_content(schema)
        _safe_content(arguments)
        json.dumps(schema, allow_nan=False)
        canonical = json.dumps(arguments, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (ValueError, TypeError) as error:
        raise SkillProposalError(INVALID_PARAMETERS) from error
    if (
        not is_supported_schema(schema)
        or not isinstance(arguments, dict)
        or validate_arguments(schema, arguments)
    ):
        raise SkillProposalError(INVALID_PARAMETERS)
    return canonical


def _safe_content(content: object) -> None:
    """Ham metin yapraklarını ve anahtarlarını JSON kaçışından önce denetle."""
    if isinstance(content, dict):
        for key, value in content.items():
            _safe_content(key)
            _safe_content(value)
    elif isinstance(content, (list, tuple)):
        for value in content:
            _safe_content(value)
    text = content if isinstance(content, str) else json.dumps(content, default=str)
    if contains_sensitive(text) or any(marker in text for marker in ("!`", "$", "{SKILL_DIR}")):
        raise SkillProposalError(UNSAFE_CONTENT)


def _proposal_payload(proposal: SkillProposal) -> dict[str, object]:
    payload = asdict(proposal)
    routine = asdict(proposal.routine)
    routine["input_schema"] = json.loads(proposal.routine.input_schema)
    payload["routine"] = routine
    return payload


def _redacted(content: object) -> object:
    """Görüntüleme için çözülmüş metinleri temizle; ardından JSON üretilebilir."""
    if isinstance(content, str):
        return redact(content)
    if isinstance(content, dict):
        return {redact(str(key)): _redacted(value) for key, value in content.items()}
    if isinstance(content, (list, tuple)):
        return [_redacted(value) for value in content]
    return content


def _skill_text(proposal: SkillProposal, plan: ExecutionPlan, arguments: str) -> str:
    """Plan yönergelerini taşı; kurulumun rutin çalıştırdığı iddiasını üretme."""
    _safe_content(_proposal_payload(proposal))
    _safe_content(asdict(plan))
    source = json.dumps(asdict(plan), ensure_ascii=False)
    description = json.dumps(proposal.routine.description, ensure_ascii=False)
    lines = [
        "---",
        f"name: {proposal.routine.routine_id}",
        f"description: {description}",
        "---",
        "# Kaydedilmiş plan rutini",
        proposal.routine.description,
        (
            "Kurulum rutini çalıştırmaz. Her kullanımda önkoşulları "
            "ve sonuç kontrollerini yeniden doğrula."
        ),
        "## Girdi şeması",
        proposal.routine.input_schema,
        "## Kurulumda doğrulanan örnek parametreler",
        arguments,
        "## Bu çağrının parametreleri",
        "$ARGUMENTS",
        "## Adımlar",
    ]
    lines.extend(f"- {step.goal}" for step in plan.steps)
    lines.extend(
        (
            "## Kaydedilmiş kontroller",
            source,
            "## Geçmiş koşum kanıtları (güncel çalıştırma kanıtı değildir)",
            json.dumps(
                [asdict(item) for item in proposal.observations], ensure_ascii=False, default=str
            ),
        )
    )
    content = "\n\n".join(lines) + "\n"
    metadata = ProposalInvocation(
        proposal.id, proposal.source_split, proposal.routine, body_revision(content)
    )
    return content.replace("---\n", "---\n" + metadata_line(metadata) + "\n", 1)


def _open_directory(path: Path) -> int:
    """Her bileşeni bağ izlemeden aç; yazmalar açık üst dizine sabitlenir."""
    if os.open not in os.supports_dir_fd or not hasattr(os, "O_NOFOLLOW"):
        raise OSError(WRITE_FAILED)
    absolute = path.absolute()
    descriptor = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in absolute.parts[1:]:
            if component in {".", ".."}:
                raise OSError(WRITE_FAILED)
            with contextlib.suppress(FileExistsError):
                os.mkdir(component, dir_fd=descriptor)
            child = os.open(
                component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _install_exclusive(root: Path, name: str, content: str) -> None:
    """Tam dosyayı atomik bağla; hatada yalnız kendi dosyanı temizle."""
    root_fd = _open_directory(root)
    skill_fd: int | None = None
    has_directory = False
    has_pending = False
    has_linked = False
    try:
        os.mkdir(name, dir_fd=root_fd)
        has_directory = True
        skill_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
        pending_fd = os.open(
            _PENDING_FILENAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=skill_fd
        )
        has_pending = True
        with os.fdopen(pending_fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(
            _PENDING_FILENAME,
            _SKILL_FILENAME,
            src_dir_fd=skill_fd,
            dst_dir_fd=skill_fd,
            follow_symlinks=False,
        )
        has_linked = True
        os.unlink(_PENDING_FILENAME, dir_fd=skill_fd)
        has_pending = False
        has_directory = False
    finally:
        if skill_fd is not None:
            try:
                if has_directory and has_linked:
                    os.unlink(_SKILL_FILENAME, dir_fd=skill_fd)
                if has_pending:
                    os.unlink(_PENDING_FILENAME, dir_fd=skill_fd)
            finally:
                os.close(skill_fd)
        try:
            if has_directory:
                os.rmdir(name, dir_fd=root_fd)
        finally:
            os.close(root_fd)
